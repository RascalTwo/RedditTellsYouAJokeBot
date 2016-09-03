*****

# /u/TellsYouAJokeBot

*****

Made for /u/palkiajack to run under /u/TellsYouAJokeBot, which tells users a joke when mentioned or a trigger phrase is found.

*****

# Dependencies

*****

- [Python 3](https://www.python.org/download/releases/3.0/)
- [Requests](http://docs.python-requests.org/en/master/)
- [PRAW](https://github.com/praw-dev/praw)

You can have the two dependencies automatically installed by executing `pip install -r requirements.txt`. You will obviously have to obtain Python and pip manually.

*****

# Configuration

*****

The configuration file - `config.json` looks like this:

```json
{
    "user_agent": "TellsYouAJokeBot/1.0 by /u/Rascal_Two for /u/palkiajack running everywhere under /u/TellsYouAJokeBot",
    "username": "",
    "password": "",
    "subreddits": [

    ],
    "reply_message": [
        "Prefix",
        "",
        "{joke}",
        "",
        "Suffix"
    ],
    "phrases": [
        "Tell me a joke"
    ],
    "trello": {
        "boards": [
            {
                "id": "u2Lq0evy",
                "list": "jokes"
            },
            {
                "id": "OYvYfI8s",
                "list": "all"
            }
        ],
        "auth": {
            "enabled": false,
            "key": "",
            "token": ""
        }
    }
}
```

*****

- `user_agent`
    - What reddit identifies the bot as. The more unique this is the better, as common user agents have their rates limited.
- `username`
    - Username of /u/TellsYouAJokeBot
- `password`
    - Password of /u/TellsYouAJokeBot
- `subreddit`
    - Extra subreddits to watch the comments of.
    - Used to watch the comments of subreddits that exclude themselfes from /r/all
- `trello`
    - Information about the Trello boards that the jokes are pulled from.
    - `boards`
        - List of boards to get jokes from.
        - `id`
            - The id of the board.
        - `list`
            - The list to get the jokes from. If `all`, all cards in the board are pulled as jokes.
    - `auth`
        - Authorization information for viewing non-public boards.
        - `enabled`
            - Is authorization enabled.
        - `key`
            - Authorization key.
        - `token`
            - Authorization token.
- `phrases`
    - List of phrases that will cause the bot to reply with a joke.
- `reply_message`
    - Message of the comment when replying to a user who is being told a joke.

*****

The text within `replay_message` can be templated with the below tags:

- `joke`
    - The actual joke.

*****

# Explanation

*****

Coming Soon

*****

The bot records all activity to the logs within the `logs` directory.

# TODO

> May do these things, may not do these things.

- Add `messages.json`
    - Allow for the customization of messages in the logger.
- Add Openshift-compatable web UI.
    - Show a log of all replies.