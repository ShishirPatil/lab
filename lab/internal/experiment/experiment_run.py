import time
from pathlib import Path, PurePath
from typing import List, Dict, Optional, Set

import numpy as np

from lab import logger
from .. import util
from ...logger import Text


def _struct_time_to_time(t: time.struct_time):
    return f"{t.tm_hour :02}:{t.tm_min :02}:{t.tm_sec :02}"


def _struct_time_to_date(t: time.struct_time):
    return f"{t.tm_year :04}-{t.tm_mon :02}-{t.tm_mday :02}"


_GLOBAL_STEP = 'global_step'


def _generate_uuid() -> str:
    from uuid import uuid1
    return uuid1().hex


class RunInfo:
    def __init__(self, *,
                 uuid: str,
                 python_file: str,
                 trial_date: str,
                 trial_time: str,
                 comment: str,
                 commit: Optional[str] = None,
                 commit_message: Optional[str] = None,
                 is_dirty: bool = True,
                 experiment_path: PurePath,
                 start_step: int = 0,
                 notes: str = '',
                 load_run: Optional[str] = None,
                 tags: List[str]):
        self.uuid = uuid
        self.commit = commit
        self.is_dirty = is_dirty
        self.python_file = python_file
        self.trial_date = trial_date
        self.trial_time = trial_time
        self.comment = comment
        self.commit_message = commit_message
        self.start_step = start_step

        self.load_run = load_run

        self.experiment_path = experiment_path
        self.run_path = experiment_path / str(uuid)
        self.checkpoint_path = self.run_path / "checkpoints"
        self.numpy_path = self.run_path / "numpy"

        self.diff_path = self.run_path / "source.diff"

        self.sqlite_path = self.run_path / "sqlite.db"
        self.tensorboard_log_path = self.run_path / "tensorboard"

        self.info_path = self.run_path / "run.yaml"
        self.indicators_path = self.run_path / "indicators.yaml"
        self.artifacts_path = self.run_path / "artifacts.yaml"
        self.configs_path = self.run_path / "configs.yaml"
        self.notes = notes
        self.tags = tags

    @classmethod
    def from_dict(cls, experiment_path: PurePath, data: Dict[str, any]):
        """
        ## Create a new trial from a dictionary
        """
        params = dict(experiment_path=experiment_path)
        params.update(data)
        return cls(**params)

    def to_dict(self):
        """
        ## Convert trial to a dictionary for saving
        """
        return dict(
            uuid=self.uuid,
            python_file=self.python_file,
            trial_date=self.trial_date,
            trial_time=self.trial_time,
            comment=self.comment,
            commit=self.commit,
            commit_message=self.commit_message,
            is_dirty=self.is_dirty,
            start_step=self.start_step,
            notes=self.notes,
            tags=self.tags,
            load_run=self.load_run
        )

    def pretty_print(self) -> List[str]:
        """
        ## 🎨 Pretty print trial for the python file header
        """

        # Trial information
        commit_status = "[dirty]" if self.is_dirty else "[clean]"
        res = [
            f"{self.trial_date} {self.trial_time}",
            self.comment,
            f"[{commit_status}]: {self.commit_message}",
            f"start_step: {self.start_step}"
        ]
        return res

    def __str__(self):
        return f"{self.__class__.__name__}(comment=\"{self.comment}\"," \
               f" commit=\"{self.commit_message}\"," \
               f" date={self.trial_date}, time={self.trial_time})"

    def __repr__(self):
        return self.__str__()

    def is_after(self, run: 'Run'):
        if run.trial_date < self.trial_date:
            return True
        elif run.trial_date > self.trial_date:
            return False
        elif run.trial_time < self.trial_time:
            return True
        else:
            return False


class Run(RunInfo):
    """
    # Trial 🏃‍

    Every trial in an experiment has same configs.
    It's just multiple runs.

    A new trial will replace checkpoints and TensorBoard summaries
    or previous trials, you should make a copy if needed.
    The performance log in `trials.yaml` is not replaced.

    You should run new trials after bug fixes or to see performance is
     consistent.

    If you want to try different configs, create multiple experiments.
    """

    diff: Optional[str]

    def __init__(self, *,
                 uuid: str,
                 python_file: str,
                 trial_date: str,
                 trial_time: str,
                 comment: str,
                 commit: Optional[str] = None,
                 commit_message: Optional[str] = None,
                 is_dirty: bool = True,
                 experiment_path: PurePath,
                 start_step: int = 0,
                 notes: str = '',
                 tags: List[str]):
        super().__init__(python_file=python_file, trial_date=trial_date, trial_time=trial_time,
                         comment=comment, uuid=uuid, experiment_path=experiment_path,
                         commit=commit, commit_message=commit_message, is_dirty=is_dirty,
                         start_step=start_step, notes=notes, tags=tags)

    @classmethod
    def create(cls, *,
               experiment_path: PurePath,
               python_file: str,
               trial_time: time.struct_time,
               comment: str,
               tags: List[str]):
        """
        ## Create a new trial
        """
        return cls(python_file=python_file,
                   trial_date=_struct_time_to_date(trial_time),
                   trial_time=_struct_time_to_time(trial_time),
                   uuid=_generate_uuid(),
                   experiment_path=experiment_path,
                   comment=comment,
                   tags=tags)

    def save_info(self):
        run_path = Path(self.run_path)
        if not run_path.exists():
            run_path.mkdir(parents=True)

        with open(str(self.info_path), "w") as file:
            file.write(util.yaml_dump(self.to_dict()))

        if self.diff is not None:
            with open(str(self.diff_path), "w") as f:
                f.write(self.diff)


def get_checkpoints(experiment_path: PurePath, run_uuid: str):
    run_path = experiment_path / run_uuid
    checkpoint_path = Path(run_path / "checkpoints")
    if not checkpoint_path.exists():
        return {}

    return {int(child.name) for child in Path(checkpoint_path).iterdir()}


def get_runs(experiment_path: PurePath):
    return {child.name for child in Path(experiment_path).iterdir()}


def get_last_run(experiment_path: PurePath, runs: Set[str]) -> Run:
    last: Optional[Run] = None
    for run_uuid in runs:
        run_path = experiment_path / run_uuid
        info_path = run_path / "run.yaml"
        with open(str(info_path), "r") as file:
            run = Run.from_dict(experiment_path, util.yaml_load(file.read()))
            if last is None:
                last = run
            elif run.is_after(last):
                last = run

    return last


def get_run_checkpoint(experiment_path: PurePath,
                       run_uuid: str, checkpoint: int = -1):
    checkpoints = get_checkpoints(experiment_path, run_uuid)
    if len(checkpoints) == 0:
        return None

    if checkpoint < 0:
        required_ci = np.max(list(checkpoints)) + checkpoint + 1
    else:
        required_ci = checkpoint

    for ci in range(required_ci, -1, -1):
        if ci not in checkpoints:
            continue

        return ci


def get_last_run_checkpoint(experiment_path: PurePath,
                            run_uuid: str,
                            checkpoint: int = -1):
    checkpoint = get_run_checkpoint(experiment_path, run_uuid,
                                    checkpoint)

    if checkpoint is None:
        logger.log("Couldn't find a previous run/checkpoint")
        return None, None

    logger.log(["Selected ",
                ("run", Text.key),
                " = ",
                (run_uuid, Text.value),
                " ",
                ("checkpoint", Text.key),
                " = ",
                (checkpoint, Text.value)])

    run_path = experiment_path / str(run_uuid)
    checkpoint_path = run_path / "checkpoints"
    return checkpoint_path / str(checkpoint), checkpoint
