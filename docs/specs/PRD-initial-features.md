Write an end-to-end command-line application for transforming an Instagram saved posts collection to Google calendar and ical events.

Features:
- point the app to an instagram saved posts collection containing events (for example music concerts)
- the app should read posts in the collection, and try to infer the event date(s), location, and event info (such as line-up / artists) from the post text and (if necessary), the post image(s)
- the app should keep a cache to keep track of what posts have already been processed, and added to what calendar, so it doesn't reprocess these posts
- to extract event data from instagram posts, the app should use OpenRouter to route the posts contents to an image-capable language model
- we should be able to specify a simple model (for handling just text), and an image capable model (to fall back to if the event data could not be inferred from text alone)
- we can choose to export direclty to ical or popular calendar file formats, or post events directly to an (existing or new) Google calendar.

User Experience:
- the app should be fairly easy and intuitive to use for non-programmers: we should expect them to be able to launch the application from the command line, but the authentication flow etc should be easy
- in order to achieve the above, we should use a simple TUI library to guide the user through the export process
- we should be able to initialize/authenticate the app once or irregularly with our Instagram account and Google account: the goal is to prevent needless re-authentication that makes the app annoying to use
- also package the app into an executable, so that the user can just run this (only target Windows for now)
- add github CI workflows to run the tests and build the executables

Constraints
- use instragrapi python module for interacting with Instagram
- we can expect users to have an OpenRouter API key. If not we can give them directions to make one
