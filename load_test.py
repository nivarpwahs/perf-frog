from utils.influxdb_client import EventInfluxHandlers
from utils.log_helper import Logger
import yaml
import os
from locust import events, TaskSet, SequentialTaskSet, HttpUser, task, between
import time

from utils.data_loader import DataLoader
from tasks.jfrog_tasks import JfrogOperations


@events.init.add_listener
def on_test_start(environment, **kwargs):
    DataLoader.load_data()
    EventInfluxHandlers.init_influx_client()

@events.quitting.add_listener
def on_test_stop(environment, **kwargs):
    pass

class LoadTestTask(HttpUser):
    host = "abc.jfrog.io"
    wait_time = between(1, 2)

    def on_start(self):
        pass

    @task
    def execute_operations(self):
        while True:
            try:
                self.test_data = DataLoader.get_data()
                operations = JfrogOperations(self)
                operations.test_data = self.test_data
                operations.run()
                delattr(self, 'test_data')
                time.sleep(2)
            except IndexError:
                self.environment.runner.quit()
                break
            except Exception:
                continue