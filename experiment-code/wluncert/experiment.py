import copy
import itertools
import os.path
import random
import time
import uuid
from typing import List, Dict

import localflow as mlflow
import numpy as np

import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm
import uuid
from analysis import ModelEvaluation
from data import SingleEnvData, Standardizer
from utils import get_date_time_uuid
import warnings


EXPERIMENT_NAME = "artif"
MLFLOW_USR = "user"
MLFLOW_PWD = "xxx"
MLFLOW_URI = f"https://{MLFLOW_USR}:{MLFLOW_PWD}@mlflow.server"

SLEEP_TIME_BASE_MAX = 0.17


def get_rnd_sleep_time():
    return np.random.uniform(0.15, SLEEP_TIME_BASE_MAX)


def mlflow_log_params(*args, **kwargs):
    time.sleep(get_rnd_sleep_time())
    # print("logging parameters")
    return mlflow.log_params(*args, **kwargs)


def mlflow_log_metrics(*args, **kwargs):
    time.sleep(get_rnd_sleep_time())
    # print("logging metrics")
    return mlflow.log_metrics(*args, **kwargs)


def mlflow_log_dict(*args, **kwargs):
    time.sleep(get_rnd_sleep_time())
    # print("logging dict")
    return mlflow.log_dict(*args, **kwargs)


class ExperimentTask:
    def __init__(
        self,
        model_lbl,
        model,
        envs_lbl,
        train_list,
        test_list,
        train_size: int,
        rel_train_size=None,
        exp_id=None,
        rnd=0,
        pooling_cat=None,
    ):
        self.model = model
        self.rnd = rnd
        self.loo_wise_predictions = {}
        self.model_lbl = model_lbl
        self.envs_lbl = envs_lbl
        self.rel_train_size = rel_train_size
        self.exp_id = exp_id
        self.train_size = train_size
        self.train_list: List[SingleEnvData] = train_list
        self.test_list: List[SingleEnvData] = test_list
        self.pooling_cat = pooling_cat
        self.training_features = self.train_list[0].get_feature_names()

    def get_metadata_dict(
        self,
    ):
        d = {
            "rnd": self.rnd,
            "model": self.model_lbl,
            "train_size": self.train_size,
            "subject_system": self.envs_lbl,
            "relative_train_size": self.rel_train_size,
            "pooling_cat": self.pooling_cat,
            "exp_id": self.exp_id,
            "n_train_features": len(self.training_features)
            # "training-feature-names": self.training_features,
        }
        # artifact_file = f"tmp/feature_names-{uuid.uuid4()}.txt"
        artifact_file = f"feature_names.txt"
        mlflow_log_dict(
            {"training_feature_names": self.training_features}, artifact_file
        )
        # os.remove(artifact_file)
        return d


class ExperimentTransfer(ExperimentTask):
    pass


class ExperimentMultitask(ExperimentTask):
    label = "multitask"

    def run(self, return_predictions=False):
        mlflow.log_params(
            {
                "rnd": self.rnd,
                "model": self.model_lbl,
                "software-system": self.envs_lbl,
                "exp_id": self.exp_id,
                "train_size": self.train_size,
                "relative_train_size": self.rel_train_size,
                "pooling_cat": self.pooling_cat,
                "experiment-type": self.label,
            }
        )
        self.model.fit(self.train_list)
        self.predictions = self.model.predict(self.test_list)
        return self.eval()

    def get_id(self):
        deterministic_id = (
            f"multitask-{self.model_lbl} on {self.envs_lbl}-trainx{self.rel_train_size}"
        )
        return deterministic_id  # self.exp_id

    def eval(self):
        meta_dict = self.get_metadata_dict()
        eval = ModelEvaluation(
            self.predictions,
            self.test_list,
        )
        eval = self.model.evaluate(eval)
        df: pd.DataFrame = eval.get_scores()

        myuuid = uuid.uuid4()

        scores_csv = os.path.abspath(
            f"tmp/multitask_scores-{self.get_id()}-{str(myuuid)}.csv"
        )
        df.to_csv(scores_csv)
        mlflow.log_artifact(scores_csv)
        os.remove(scores_csv)
        df_annotated = df.assign(**meta_dict)
        model_meta_data = eval.get_metadata()
        model_meta_data_annotated = model_meta_data.assign(**meta_dict)
        return df_annotated, model_meta_data_annotated


class Replication:
    def __init__(
        self,
        experiment_classes,
        models: Dict,
        data_providers: Dict,
        train_sizes_relative_to_option_number,
        rnds=None,
        n_jobs=False,
        replication_lbl="last-experiment",
        plot=False,
        do_transfer_task=False,
    ):
        self.replication_lbl = get_date_time_uuid() + "-" + replication_lbl
        self.progress_bar = None
        self.plot = plot
        self.models = models
        self.experiment_classes = experiment_classes
        self.n_jobs = n_jobs
        self.data_providers = data_providers
        self.train_sizes_relative_to_option_number = (
            train_sizes_relative_to_option_number
        )
        self.rnds = rnds if rnds is not None else [0]
        self.result = None
        self.do_transfer_task = do_transfer_task
        self.parent_run_id = None
        self.experiment_name = f"uncertainty-learning-{self.replication_lbl}"

    def run(self):
        # if not mlflow.create_experiment(experiment_name):
        # mlflow.set_tracking_uri(
        #
        # )
        # mlflow.set_experiment(experiment_name=self.experiment_name)

        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment(experiment_name=EXPERIMENT_NAME)
        run_name = self.experiment_name.replace(" ", "")
        with mlflow.start_run(run_name=run_name) as run:
            self.parent_run_id = run.info.run_id
            print(self.parent_run_id)
        time.sleep(0.2)
        # mlflow.end_run()

        tasks = {key: [] for key in self.experiment_classes}
        for model_lbl, model_proto in self.models.items():
            for data_lbl, data_set in self.data_providers.items():
                max_train_size = max(self.train_sizes_relative_to_option_number)
                for train_size in self.train_sizes_relative_to_option_number:
                    for rnd in self.rnds:
                        data_per_env: List[
                            SingleEnvData
                        ] = data_set.get_workloads_data()
                        train_list = []
                        test_list = []

                        rng = np.random.default_rng(rnd)
                        seeds = [
                            rng.integers(0, 2**30, dtype=np.uint32)
                            for r in range(len(data_per_env))
                        ]
                        for i, env_data in zip(seeds, data_per_env):
                            # new_seed_for_env = rng.integers(0, 2**30, dtype=np.uint32)
                            new_seed_for_env = i
                            split = env_data.get_split(
                                rnd=new_seed_for_env,
                                n_train_samples_rel_opt_num=train_size,
                                n_test_samples_rel_opt_num=max_train_size,
                            )
                            train_data = split.train_data
                            train_list.append(train_data)
                            test_list.append(env_data)
                        abs_train_size = len(train_list[0])
                        for task_class in self.experiment_classes:
                            model_proto_for_env = copy.deepcopy(model_proto)
                            model_proto_for_env.set_envs(data_set)
                            pooling_cat = model_proto_for_env.get_pooling_cat()
                            new_task = task_class(
                                model_lbl,
                                model_proto_for_env,
                                data_lbl,
                                train_list,
                                test_list,
                                train_size=abs_train_size,
                                pooling_cat=pooling_cat,
                                rel_train_size=train_size,
                                exp_id=self.experiment_name,
                                rnd=rnd,
                            )
                            tasks[task_class].append(new_task)

        print("provisioned experiments", flush=True)

        random.seed(self.rnds[0])
        # results = {key: [] for key in tasks}
        # scores_list = []
        # metas_list = []
        # result_dict = {}
        for task_type in tasks:
            random.shuffle(tasks[task_type])
            print(f"Planning {self.n_jobs} jobs")

            if self.n_jobs:
                Parallel(n_jobs=self.n_jobs)(
                    delayed(self.handle_task)(task) for task in tqdm(tasks[task_type])
                )
            else:
                self.progress_bar = tqdm(
                    total=len(tasks),
                    desc="Running multitask learning tasks",
                    unit="task",
                )
                for type_wise_tasks in tasks[task_type]:
                    self.handle_task(type_wise_tasks)
                    # self.progress_bar.update(1)
                self.progress_bar.close()
        print(self.parent_run_id)
        return self.parent_run_id

    # def handle_task(self, progress_bar, task):
    def handle_task(self, task: ExperimentTask):
        mlflow.set_tracking_uri(MLFLOW_URI)
        mlflow.set_experiment(experiment_name=EXPERIMENT_NAME)
        # mlflow.set_experiment(experiment_name=self.experiment_name)
        run_name = task.get_id()
        with mlflow.start_run(
            run_id=self.parent_run_id  # self.experiment_name.replace(" ", ""),
        ):
            with mlflow.start_run(run_name=run_name, nested=True):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=UserWarning)
                    task.run()
        del task.model
        del task
