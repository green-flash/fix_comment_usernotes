# fix_comment_usernotes
A script to fix botched usernote comment links introduced by reddit-moderator-toolbox 3.1 (issue #534)

### Background

https://github.com/creesch/reddit-moderator-toolbox/issues/534

When creating a usernote on a comment, Toolbox 3.1 always stored a link to the submission, not a the comment. 
This has been fixed in 3.1.1, but any comment-related usernotes saved in the two weeks between the two releases are mostly useless.

### Fix

This script checks all usernotes created between release 3.1 and 3.1.1 of reddit-moderator-toolbox and attempts to recreate the connection to the respective user's **removed comments**. It assumes that comment usernotes are only created for removed comments. It will not do anything useful with usernotes for comments that have not been removed.

### Procedure

For all notes linking to a submission it searches the user's profile for removed comments in the comments section of the respective submission.

- If it finds **exactly one such comment** for a usernote, it updates the usernote link to point towards that comment.
- If it finds **more than one such comment** for a usernote, it adds a comment to a helper submission listing all the qualifying comments and updates the usernote to point towards that helper comment. The helper submission id must be manually specified. It must be in the same subreddit.

Depending on how many usernotes were created, the script may take a while. It updates the usernotes wiki page in batches. It can also be run in **dry mode** to first inspect what would happen.
