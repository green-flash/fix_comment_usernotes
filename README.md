# fix_comment_usernotes
A script to fix the botched usernote comment links introduced by reddit-moderator-toolbox 3.1 (issue #534)

https://github.com/creesch/reddit-moderator-toolbox/issues/534

Toolbox 3.1 always stored a link to the submission, not the comment. 
This has been fixed in 3.1.1, but any comment-related usernotes saved in between are useless.

This script checks all usernotes created between release 3.1 and 3.1.1 of reddit-moderator-toolbox.

For all notes linking to a submission it searches the user's comments for removed comments in the comments section of the respective submission.

If it finds one such note, it updates the usernote link to point towards that comment.
If it finds more than one such note, it adds a comment to a helper submission listing all the qualifying comments 
and updates the usernote to point towards that helper comment.

Depending on how many usernotes were created, the script may take a while. It updates the usernotes wiki page in batches.
