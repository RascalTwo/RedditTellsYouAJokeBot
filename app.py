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
import json
import time
import praw
import random
import logging
import logging.handlers
import requests
import threading

class Loop():
    def __init__(self, function, name=None):
        self.function = function
        thread = threading.Thread(target=self.function, name=name)
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
        self.processed = self._load_file("data/processed.json", False)
        self.config = self._load_file("config.json")
        self.trello = self._load_file("data/trello.json")
        self.jokes = self._load_file("data/jokes.json")

        self.reply_to = []

        self.reddit = praw.Reddit(self.config["user_agent"])
        self.reddit.login(self.config["username"],
                          self.config["password"],
                          disable_warning="True")

    def _load_file(self, name, return_dict=True):
        try:
            with open(name, "r") as reading_file:
                return json.loads(reading_file.read())
        except:
            with open(name, "w") as writing_file:
                if return_dict:
                    writing_file.write(json.dumps({}))
                else:
                    writing_file.write(json.dumps([]))

            if return_dict:
                return {}
            return []

    def _save_file(self, name, data):
        with open(name, "w") as writing_file:
            writing_file.write(json.dumps(data))

    def run(self):
        Loop(self._trello_loop, "Trello")
        Loop(self._mentions_loop, "Mentions")
        Loop(self._comment_loop, "Comments")

        uptime = 0
        while True:
            logger.info("Uptime: {}s".format(uptime))
            # Don't use a for loop on `reply_to`, it is constantly being changed.
            # Instead remove every element one by one
            while True:
                if len(self.reply_to) == 0:
                    break
                thing = self.reply_to.pop(0)
                logger.info(thing.id + " " + thing.author.name)
                logger.info(self.get_random_joke())
                #Here goes reply
            time.sleep(self.config["rates"]["reply"])

    def _trello_loop(self):
        while True:
            if self.trello_changed():
                logger.info("Trello change detected.")
                self._save_file("data/trello.json", self.trello)
                modified = False
                for joke in self.get_trello_jokes():
                    if joke["id"] in self.jokes:
                        if joke["text"] == self.jokes[joke["id"]]:
                            continue
                        self.jokes[joke["id"]] = joke["text"]
                        modfiied = True
                        continue
                    if joke["id"] not in self.jokes:
                        self.jokes[joke["id"]] = joke["text"]
                        modified = True
                if modified:
                    logger.info("Joke(s) updated.")
                    self._save_file("data/jokes.json", self.jokes)

            time.sleep(self.config["rates"]["trello"])

    def _mentions_loop(self):
        while True:
            for mention in self.reddit.get_mentions():
                if mention.id in self.processed:
                    continue
                logger.info("Username mentioned by " + mention.author.name + ".")
                self.reply_to.append(mention)
                self.processed.append(mention.id)
                self._save_file("data/processed.json", self.processed)
            time.sleep(self.config["rates"]["mentions"])

    def _comment_loop(self):
        for comment in praw.helpers.comment_stream(self.reddit, "all+" + "+".join(self.config["subreddits"]), verbosity=0):
            if comment.id in self.processed:
                continue
            if self.should_reply_to(comment.body):
                logger.info("Valid phrase detected in '" + comment.author.name + "'s comment.")
                self.reply_to.append(comment)
                continue
            self.processed.append(comment.id)
            self._save_file("data/processed.json", self.processed)

    def should_reply_to(self, body):
        for phrase in self.config["phrases"]:
            if phrase.lower() in body.lower():
                return True
        return False

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
        if self.config["trello"]["auth"]["required"]:
            return ("{}key={}&token={}"
                    .format(prefix,
                            self.config["trello"]["auth"]["key"],
                            self.config["trello"]["auth"]["token"]))
        return ""

    def trello_changed(self):
        auth = self._get_trello_auth(prefix="&")
        for board in self.config["trello"]["boards"]:
            board = self._get_last_activity(board["id"], "board", auth)
            if board["id"] not in self.trello:
                self.trello[board["id"]] = board["dateLastActivity"]
                return True
            if self.trello[board["id"]] != board["dateLastActivity"]:
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


if __name__ == "__main__":
    logging_format = logging.Formatter("[%(asctime)s] [%(threadName)s] [%(levelname)s]: %(message)s")
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

    TellsYouAJokeBot().run()
