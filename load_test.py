from utils.influxdb_client import EventInfluxHandlers
from utils.log_helper import Logger
import yaml
import os

from locust import events, TaskSet, SequentialTaskSet, HttpUser
from utils.data_loader import DataLoader
from tasks.jfrog_tasks import JfrogOperations


@events.init.add_listener
def on_test_start(**kwargs):
    DataLoader.load_data()  # Load data only once at the start
    EventInfluxHandlers.init_influx_client()
    Logger.log_message("--------Initiating Tests---------")

@events.quitting.add_listener
def on_test_stop(**kwargs):
    Logger.log_message("........ Load Test Completed ........")

class LoadTestTask(HttpUser):
    host = "trial9zttz8.jfrog.io"  # This will be overridden by command line --host parameter
    tasks = [JfrogOperations]
    wait_time = 1  # Add a small wait time between tasks

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.taskset = JfrogOperations(self)

    def run(self):
        self.taskset.run()