"""
title: Llama Index DB Pipeline
author: 0xThresh
date: 2024-07-01
version: 1.0
license: MIT
description: A pipeline for using text-to-SQL for retrieving relevant information from a database using the Llama Index library.
requirements: llama_index, sqlalchemy, psycopg2-binary
"""

from typing import List, Union, Generator, Iterator
import os 
from llama_index.llms.ollama import Ollama
from llama_index.core.query_engine import NLSQLTableQueryEngine
from llama_index.core import SQLDatabase, PromptTemplate
from sqlalchemy import create_engine


class Pipeline:
    def __init__(self):
        self.PG_HOST = os.environ["PG_HOST"]
        self.PG_PORT = os.environ["PG_PORT"]
        self.PG_USER = os.environ["PG_USER"]
        self.PG_PASSWORD = os.environ["PG_PASSWORD"]
        self.PG_DB = os.environ["PG_DB"]
        self.ollama_host = "http://host.docker.internal:11434" # Make sure to update with the URL of your Ollama host, such at http://localhost:11434 or remote server address
        self.model = "phi3:medium-128k" # Model to use for text-to-SQL generation
        self.engine = None
        self.nlsql_response = ""
        self.tables = ["db_table"] # Update to the name of the database table you want to get data from

    def init_db_connection(self):
        self.engine = create_engine(f"postgresql+psycopg2://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}")
        return self.engine


    async def on_startup(self):
        # This function is called when the server is started.
        self.init_db_connection()

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # Debug logging is required to see what SQL query is generated by the LlamaIndex library; enable on Pipelines server if needed

        # Create database reader for Postgres
        sql_database = SQLDatabase(self.engine, include_tables=self.tables)

        # Set up LLM connection; uses phi3 model with 128k context limit since some queries have returned 20k+ tokens
        llm = Ollama(model=self.model, base_url=self.ollama_host, request_timeout=180.0, context_window=30000)

        # Set up the custom prompt used when generating SQL queries from text
        text_to_sql_prompt = """
        Given an input question, first create a syntactically correct {dialect} query to run, then look at the results of the query and return the answer. 
        You can order the results by a relevant column to return the most interesting examples in the database.
        Unless the user specifies in the question a specific number of examples to obtain, query for at most 5 results using the LIMIT clause as per Postgres. You can order the results to return the most informative data in the database.
        Never query for all the columns from a specific table, only ask for a few relevant columns given the question.
        You should use DISTINCT statements and avoid returning duplicates wherever possible.
        Pay attention to use only the column names that you can see in the schema description. Be careful to not query for columns that do not exist. Pay attention to which column is in which table. Also, qualify column names with the table name when needed. You are required to use the following format, each taking one line:

        Question: Question here
        SQLQuery: SQL Query to run
        SQLResult: Result of the SQLQuery
        Answer: Final answer here

        Only use tables listed below.
        {schema}

        Question: {query_str}
        SQLQuery: 
        """

        text_to_sql_template = PromptTemplate(text_to_sql_prompt)

        query_engine = NLSQLTableQueryEngine(
            sql_database=sql_database, 
            tables=self.tables, 
            llm=llm, 
            embed_model="local", 
            text_to_sql_prompt=text_to_sql_template, 
            streaming=True
        )

        response = query_engine.query(user_message)

        return response.response_gen

