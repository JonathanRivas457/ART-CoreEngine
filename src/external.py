"""
ART-CoreEngine - 2024 - Benjamin Carter 

This file holds the outbound API calls that the UI team can later use.
It is meant to be imported into any external application

The contents of this class shall not depend on anything external.
It must be self contained.

"""

import json
import os
import pickle
from joblib import Memory

import pandas as pd
from src.database_manager import DatabaseManager
from src.open_issue_classification import (
    generate_system_message,
    get_gpt_response_one_issue,
    clean_text_rf,
    predict_open_issues,
)
from src.issue_class import Issue


class External_Model_Interface:
    def __init__(
        self,
        open_ai_key: str,
        db: DatabaseManager,
        model_file: str,
        domain_file: str,
        response_cache: str,
    ):

        with open(model_file, "rb") as f:
            self.model = pickle.load(f)

        with open(domain_file, "r") as f:
            self.domains = json.load(f)

        self.db = db
        self.model_file_name = model_file
        self.__open_ai_key = open_ai_key
        self.memory = Memory(response_cache)
        self.__cached_pi = self.memory.cache(self.__predict_issue, ignore=["num"])

    def predict_issue(self, issue: Issue):
        # Simply to force new cache if model changes.
        cache_unique = f"{self.model['type']} {self.model_file_name}"
        return self.__cached_pi(issue.number, issue.title, issue.body, cache_unique)

    def __predict_issue(self, num, title, body, _ignore_me):

        issue = Issue(num, title, body)  # for caching.

        if self.model["type"] == "gpt":
            return self.__gpt_predict(issue)
        elif self.model["type"] == "rf":
            return self.__rf_predict(issue)
        else:
            raise NotImplementedError("Model type not recognized")

    def __gpt_predict(self, issue: Issue):
        llm_classifier = self.model["model"]

        columns = self.db.get_df_column_names()
        empty = [list(range(len(columns)))]
        df = pd.DataFrame(data=empty, columns=columns)

        system_message, assistant_message = generate_system_message(self.domains, df)

        # equiv to get_gpt_responses()
        response = get_gpt_response_one_issue(
            issue, llm_classifier, system_message, self.__open_ai_key
        )

        return response

    def __rf_predict(self, issue: Issue):
        clf = self.model["model"]
        vx = self.model["vectorizer"]
        y_df = self.model["labels"]

        df = pd.DataFrame(columns=["Issue #", "Title", "Body"], data=[issue.get_data()])
        vectorized_text = clean_text_rf(vx, df)

        # predict open issues ()
        predictions = predict_open_issues(df, clf, vectorized_text, y_df)

        value_out: list[int] = []
        columns: list[str] = []
        for column in predictions.columns:
            if len(column) < 3 or column == "Issue #":
                continue
            value = predictions[column][0]

            if len(value_out) == 0:
                value_out.insert(0, value)
                columns.insert(0, column)
            else:
                x = 0
                while x < len(value_out) and value_out[x] > value:
                    x += 1
                value_out.insert(x, value)
                columns.insert(x, column)

        return columns[:3]
