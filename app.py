#!/usr/bin/env python3

# The MIT License (MIT)

# Copyright (c) 2016 RascalTwo @ therealrascaltwo@gmail.com

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import re
import json
import time
import praw
import random
import logging
import logging.handlers
import requests
import threading

class Thread():
    def __init__(self, function, name=None, args=None):
        self.function = function
        thread = threading.Thread(target=self.function, name=name, args=args)
        thread.daemon = True
        thread.start()

class HTTPException(Exception):
    pass

def handle_response(response_expected):
    """Decorator to catch errors within request responses."""
    def wrap(function):
        def function_wrapper(*args, **kwargs):
            """Function wrapper."""
            response = function(*args, **kwargs)
            if response.status_code != 200:
                logger.critical(response.text)
                raise HTTPException("'{}' requesting '{}' returned a status code of {}"
                                    .format(function.__name__,
                                            response.url,
                                            response.status_code))
            if response_expected == "json":
                try:
                    return response.json()
                except Exception as exception:
                    logger.critical("'{}' requesting '{}' expected 'json' response."
                                    .format(function.__name__,
                                            response.url))
                    logger.exception(exception)
            return response.text
        return function_wrapper
    return wrap


class TellsYouAJokeBot(object):
    def __init__(self):
        self.processed = self._load_file("data/processed.json")
        self.messages = self._load_file("messages.json")
        self.config = self._load_file("config.json")
        self.trello = self._load_file("data/trello.json")
        self.jokes = self._load_file("data/jokes.json")

        if self.processed == {}:
            self.processed = {
                "mentions": [],
                "comments": []
            }

        self.io = {
            "data/processed.json": {
                "save": False,
                "attribute": "processed"
            },
            "data/trello.json": {
                "save": False,
                "attribute": "trello"
            },
            "data/jokes.json": {
                "save": False,
                "attribute": "jokes"
            },
        }

        self.uptime = 0

        self.reply_to = []

        self.reddit = praw.Reddit(self.config["user_agent"])
        self.reddit.login(self.config["username"],
                          self.config["password"],
                          disable_warning="True")

    def _load_file(self, name, new=True):
        try:
            with open(name, "r") as reading_file:
                return json.loads(reading_file.read())
        except Exception as exception:
            if new:
                with open(name, "w") as writing_file:
                    if return_dict:
                        writing_file.write(json.dumps({}))
                    else:
                        writing_file.write(json.dumps([]))
            else:
                logger.exception(exception)

            if return_dict:
                return {}
            return []

    def _save_file(self, name, attribute):
        with open(name, "w") as writing_file:
            writing_file.write(json.dumps(getattr(self, attribute)))

    def mark_for_saving(self, name):
        if not self.io[name]["save"]:
            self.io[name]["save"] = True

    def start(self):
        self.running = True
        rates = {}
        for process in self.config["rates"]:
            if self.config["rates"][process] in rates:
                rates[self.config["rates"][process]].append(process.capitalize())
            else:
                rates[self.config["rates"][process]] = [process.capitalize()]

        log(self.messages["thread_init"],
            {"num": 1, "thread_name": "Comments"})

        for rate in rates:
            rates[rate].sort()
            thread_name = "-".join(rates[rate])
            log(self.messages["thread_init"],
                {"num": list(rates.keys()).index(rate) + 2, "thread_name": thread_name})
            if self.config["shorten_thread_names"]:
                thread_name = "-".join([process[0] for process in rates[rate]])
            Thread(self._loop_runner,
                   thread_name,
                   [[getattr(self, "_{}_loop".format(loop.lower())) for loop in rates[rate]], rate])


        for comment in praw.helpers.comment_stream(self.reddit, "all+" + "+".join(self.config["subreddits"]), verbosity=0):
            if not self.running:
                break
            if comment.id in self.processed["comments"]:
                continue
            if self.should_reply_to(comment):
                log(self.messages["phrase_found"], {"comment": comment})
                self.reply_to.append(comment)
            self.add_comment_id(comment.id)
            self.mark_for_saving("data/processed.json")

    def stop(self):
        self.running = False

    def _loop_runner(self, loops, rate):
        while self.running:
            for loop in loops:
                loop()
            time.sleep(rate)

    def _trello_loop(self):
        if self.trello_changed():
            log(self.messages["trello_changed"])
            self.mark_for_saving("data/trello.json")
            modified = False
            for joke in self.get_trello_jokes():
                if joke["id"] in self.jokes:
                    if joke["text"] == self.jokes[joke["id"]]:
                        continue
                    self.jokes[joke["id"]] = joke["text"]
                    modified = True
                    continue
                if joke["id"] not in self.jokes:
                    self.jokes[joke["id"]] = joke["text"]
                    modified = True
            if modified:
                log(self.messages["jokes_updated"])
                self.mark_for_saving("data/jokes.json")

    def _mentions_loop(self):
        for comment in self.reddit.get_mentions():
            if comment.id in self.processed["mentions"]:
                continue
            log(self.messages["username_mention"], {"comment": comment})
            self.reply_to.append(comment)
            self.processed["mentions"].append(comment.id)
            self.mark_for_saving("data/processed.json")

    def _reply_loop(self):
        while True:
            if len(self.reply_to) == 0:
                break
            comment = self.reply_to.pop(0)
            reply = comment.reply(self.get_formated_message(comment))
            log(self.messages["reply"], {"comment": comment})
            self.add_comment_id(reply.id)
            self.mark_for_saving("data/processed.json")

    def _io_loop(self):
        for file in self.io:
            if self.io[file]["save"]:
                self._save_file(file, self.io[file]["attribute"])
                self.io[file]["save"] = False

    def _uptime_loop(self):
        log(self.messages["uptime"], {"uptime": self.uptime})
        self.uptime += self.config["rates"]["uptime"]

    def add_comment_id(self, id):
        self.processed["comments"].append(id)
        if len(self.processed["comments"]) > self.config["max_comments"]:
            self.processed["comments"] = self.processed["comments"][int(self.config["max_comments"] / 2):-1]

    def should_reply_to(self, comment):
        if comment.author.name in self.config["ignored_users"]:
            return False
        for phrase in self.config["phrases"]:
            if phrase.lower() in comment.body.lower():
                return True
        for regex_exp in self.config["regex_expressions"]:
            if re.search(regex_exp, comment.body):
                return True

        return False

    def get_formated_message(self, comment):
        return ("\n".join(self.config["reply_message"])
                .format(joke=self.get_random_joke(),
                        comment=comment))

    @handle_response("json")
    def _get_children_of_parent(self, parent, auth, parent_type, child):
        return requests.get("https://api.trello.com/1/{}s/{}/{}s{}"
                            .format(parent_type, parent, child, auth))

    def _get_board_cards(self, board, auth):
        return self._get_children_of_parent(board, auth, "board", "card")

    def _get_board_lists(self, board, auth):
        return self._get_children_of_parent(board, auth, "board", "list")

    def _get_list_cards(self, list, auth):
        return self._get_children_of_parent(list, auth, "list", "card")

    @handle_response("json")
    def _get_last_activity(self, target, target_type, auth):
        return requests.get("https://api.trello.com/1/{}s/{}?fields=dateLastActivity,{}"
                            .format(target_type, target, auth))

    def _get_trello_auth(self, prefix="?"):
        if self.config["trello"]["auth"]["enabled"]:
            return ("{}key={}&token={}"
                    .format(prefix,
                            self.config["trello"]["auth"]["key"],
                            self.config["trello"]["auth"]["token"]))
        return ""

    def trello_changed(self):
        auth = self._get_trello_auth(prefix="&")
        for board in self.config["trello"]["boards"]:
            board = self._get_last_activity(board["id"], "board", auth)
            if board["id"] not in self.trello or self.trello[board["id"]] != board["dateLastActivity"]:
                self.trello[board["id"]] = board["dateLastActivity"]
                return True

        return False

    def get_trello_jokes(self):
        auth = self._get_trello_auth()

        cards = []

        for board in self.config["trello"]["boards"]:
            if (board["list"] == "all"):
                cards.extend(self._get_board_cards(board["id"], auth))
                continue
            lists = self._get_board_lists(board["id"], auth)
            for card_list in lists:
                if card_list["name"].lower() != board["list"].lower():
                    continue
                cards.extend(self._get_list_cards(card_list["id"], auth))

        return [{"id": card["id"], "text": card["desc"]} for card in cards]

    def get_random_joke(self):
        return self.jokes[random.choice(list(self.jokes.keys()))]


def log(message, args=None):
    if args is None:
        logger.info(message)
    else:
        logger.info(message.format(**args))


if __name__ == "__main__":
    logging_format = logging.Formatter("[%(asctime)s] [%(threadName)s]: %(message)s")
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    file_logger = logging.handlers.TimedRotatingFileHandler("logs/output.log",
                                                            when="midnight",
                                                            interval=1)
    file_logger.setFormatter(logging_format)
    logger.addHandler(file_logger)

    console_logger = logging.StreamHandler()
    console_logger.setFormatter(logging_format)
    logger.addHandler(console_logger)

    bot = TellsYouAJokeBot()
    try:
        bot.start()
    except (KeyboardInterrupt, SystemExit):
        bot.stop()
        for file in bot.io:
            if bot.io[file]["save"]:
                log(bot.messages["saving"])
                bot._save_file(file, bot.io[file]["attribute"])
                log(bot.messages["saved"])
        log(bot.messages["shutdown"])
