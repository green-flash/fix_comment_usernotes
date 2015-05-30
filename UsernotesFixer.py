from collections import defaultdict
import sys, os
import logging, logging.config
import praw
import json

from ConfigParser import SafeConfigParser


cfg_file = SafeConfigParser()
path_to_cfg = os.path.abspath(os.path.dirname(sys.argv[0]))
path_to_cfg = os.path.join(path_to_cfg, 'fixusernotes.cfg')
cfg_file.read(path_to_cfg)
logging.config.fileConfig(path_to_cfg)

DRY_RUN = False

TOOLBOX_3_1_RELEASE_UTC_TIMESTAMP = 1431727342
TOOLBOX_3_1_1_RELEASE_UTC_TIMESTAMP_PLUS_24H = 1432835917

# global reddit session
r = None


def get_submission_id(usernote):
    link_ids = usernote['l'].split(',')
    if link_ids[0] == 'l' and len(link_ids) == 2:
        return link_ids[1]
    else:
        return None


def get_and_verify_helper_submission(helper_submission_id, subreddit_name):
    try:
        helper_submission = r.get_submission(submission_id=helper_submission_id)
    except Exception as e:
        logging.exception(e)
        raise Exception('Could not access helper submission with id {0}'.format(helper_submission_id))
    if not helper_submission.subreddit.display_name == subreddit_name:
        raise Exception('Helper submission is in /r/{0}, must be in /r/{1} for fallback usernotes to work'.format(
            helper_submission.subreddit.display_name, subreddit_name))
    return helper_submission


def find_qualifying_usernotes(usernotes_entry, start_timestamp_utc, stop_timestamp_utc):
    qualifying_usernotes_by_submission_id = defaultdict(list)
    usernotes_by_most_recent_first = sorted(usernotes_entry['ns'], key=lambda x: x['t'], reverse=True)

    for usernote in usernotes_by_most_recent_first:
        if stop_timestamp_utc < usernote['t']:
            continue
        if usernote['t'] < start_timestamp_utc:
            break
        submission_id = get_submission_id(usernote)
        if submission_id:
            qualifying_usernotes_by_submission_id[submission_id].append(usernote)

    return qualifying_usernotes_by_submission_id


def find_qualifying_comments(qualifying_usernotes_by_submission_id, user):
    qualifying_comments_by_submission_id = defaultdict(list)
    for comment in user.get_comments(limit=None):
        submission_id_without_prefix = comment.link_id[3:]
        if submission_id_without_prefix in qualifying_usernotes_by_submission_id and comment.banned_by:
            qualifying_comments_by_submission_id[submission_id_without_prefix].append(comment)
        if comment.created_utc < TOOLBOX_3_1_RELEASE_UTC_TIMESTAMP:
            break
    return qualifying_comments_by_submission_id


def redirect_usernote_to_removed_comment(username, only_candidate_comment_id, qualifying_usernote, submission_id):
    logging.info('Redirecting usernote \'{0}\' for user {1} to their only removed comment in {2}: {3}'.format(
        qualifying_usernote['n'], username, submission_id, only_candidate_comment_id.permalink.encode('utf-8')))
    qualifying_usernote['l'] = ','.join(['l', submission_id, only_candidate_comment_id.id])


def redirect_usernote_to_helper_comment(username, candidate_comments_for_submission, qualifying_usernote,
                                        submission_id, helper_submission):
    comments_as_markdown = '\n'.join(
        map(lambda comm: ' * {0}?context=3'.format(comm.permalink.encode('utf-8')), candidate_comments_for_submission))
    number_of_candidates = len(candidate_comments_for_submission)
    logging.info('Redirecting usernote \'{0}\' for user {1} '
                 'to a helper comment with all {2} candidate links in submission {3}: \n{4}'.format(
                    qualifying_usernote['n'], username, number_of_candidates, submission_id, comments_as_markdown))

    if not DRY_RUN:
        comment_text = 'Botched usernote, probably one of the following comments:\n\n{0}'.format(comments_as_markdown)
        helper_comment = helper_submission.add_comment(comment_text)
        qualifying_usernote['l'] = ','.join(['l', helper_submission.id, helper_comment.id])


def process_qualifying_usernotes(username, qualifying_usernotes_by_submission_id, helper_submission):
    user = r.get_redditor(username)
    qualifying_comments_by_submission_id = find_qualifying_comments(qualifying_usernotes_by_submission_id, user)

    for submission_id, qualifying_usernotes in qualifying_usernotes_by_submission_id.items():
        if submission_id in qualifying_comments_by_submission_id:
            candidate_comments_for_submission = qualifying_comments_by_submission_id[submission_id]
            for qualifying_usernote in qualifying_usernotes:
                if len(candidate_comments_for_submission) == 1:
                    redirect_usernote_to_removed_comment(username, candidate_comments_for_submission[0],
                                                         qualifying_usernote, submission_id)
                else:
                    redirect_usernote_to_helper_comment(username, candidate_comments_for_submission,
                                                        qualifying_usernote, submission_id, helper_submission)
        else:
            qualifying_submission = r.get_submission(submission_id=submission_id)
            for qualifying_usernote in qualifying_usernotes:
                if not qualifying_submission.author:
                    possible_explanation = 'might be a submission note as submitter is [deleted]'
                elif qualifying_submission.author.name == username:
                    possible_explanation = 'might be a submission note as user is submitter'
                else:
                    possible_explanation = 'user might have deleted the comment'
                logging.info('usernote \'{0}\' for user {1}: no removed comments found in submission {2} - {3}'.format(
                    qualifying_usernote['n'], username, qualifying_submission, possible_explanation))


def main():
    global r

    try:
        r = praw.Reddit(user_agent=cfg_file.get('reddit', 'user_agent'))
        r.config.decode_html_entities = True
        access_username = cfg_file.get('reddit', 'username')
        access_password = cfg_file.get('reddit', 'password')
        logging.info('Logging in as {0}'.format(access_username))
        r.login(access_username, access_password)
        logging.debug('Logged in successfully')

        subreddit_name = cfg_file.get('fix_usernotes', 'subreddit_name')
        helper_submission_id = cfg_file.get('fix_usernotes', 'helper_submission_id')

        helper_submission = get_and_verify_helper_submission(helper_submission_id, subreddit_name)

        # batches of 12 hours to reduce time between wiki page read and write
        batch_timedelta_in_seconds = (60 * 60 * 12)

        for stop_timestamp_utc in range(TOOLBOX_3_1_1_RELEASE_UTC_TIMESTAMP_PLUS_24H,
                                        TOOLBOX_3_1_RELEASE_UTC_TIMESTAMP,
                                        -batch_timedelta_in_seconds):

            start_timestamp_utc = max(stop_timestamp_utc - batch_timedelta_in_seconds,
                                      TOOLBOX_3_1_RELEASE_UTC_TIMESTAMP)

            logging.info('Starting batch from {0} to {1}'.format(stop_timestamp_utc, start_timestamp_utc))

            logging.info('loading wikipage data')
            usernotes_wiki_page = r.get_wiki_page(subreddit_name, 'usernotes')
            json_data = json.loads(usernotes_wiki_page.content_md)
            logging.info('done loading wikipage data')

            users = json_data['users']

            logging.info('checking users for botched comment usernotes')

            for username, usernotes_entry in users.items():

                qualifying_usernotes_by_submission_id = find_qualifying_usernotes(usernotes_entry,
                                                                                  start_timestamp_utc,
                                                                                  stop_timestamp_utc)

                if qualifying_usernotes_by_submission_id:

                    number_of_qualifying_usernotes = sum(len(v) for v in qualifying_usernotes_by_submission_id.values())
                    logging.info('user {0}: Found {1} potentially botched usernote(s), by submission id: {2}'.format(
                        username, number_of_qualifying_usernotes, qualifying_usernotes_by_submission_id))

                    try:
                        process_qualifying_usernotes(username, qualifying_usernotes_by_submission_id, helper_submission)
                    except Exception:
                        logging.exception('Failed to process qualifying usernotes of user {0}'.format(username))

            if not DRY_RUN:
                logging.info('writing updated wikipage data')
                json_dump = json.dumps(json_data, separators=(',', ':'))
                wikipage_edit_reason = 'Fixing botched usernotes created by Toolbox 3.1 between {0} and {1}'.format(
                    stop_timestamp_utc, start_timestamp_utc)
                r.edit_wiki_page(subreddit_name, 'usernotes', json_dump, wikipage_edit_reason)
                logging.info('done writing updated wikipage data')

    except Exception as e:
        logging.error('ERROR: {0}'.format(e))
    finally:
        logging.info("done.")


if __name__ == '__main__':
    main()
