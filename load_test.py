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
    DataLoader.load_data()  # Load data only once at the start
    EventInfluxHandlers.init_influx_client()
    Logger.log_message("--------Initiating Tests---------")

@events.quitting.add_listener
def on_test_stop(environment, **kwargs):
    Logger.log_message("........ Load Test Completed ........")

class LoadTestTask(HttpUser):
    host = "abc.jfrog.io"  # This will be overridden by command line --host parameter
    wait_time = between(1, 2)  # Wait between 1 and 2 seconds between tasks

    def on_start(self):
        """Initialize when user starts"""
        Logger.log_message(f"Starting user with host: {self.host}")

    @task
    def execute_operations(self):
        """Execute all JFrog operations in sequence"""
        while True:  # Continue until no more data is available
            try:
                # Get the next available data for this user
                self.test_data = DataLoader.get_data()
                Logger.log_message(f"User got data: {self.test_data}")
                
                # Execute operations with this data
                operations = JfrogOperations(self)
                operations.test_data = self.test_data
                operations.run()
                
                # Clear the test data to force getting new data in next iteration
                delattr(self, 'test_data')
                
                # Add a small delay between data sets
                time.sleep(2)
                
            except IndexError:
                Logger.log_message("No more test data available. Stopping user.")
                self.environment.runner.quit()
                break
            except Exception as e:
                Logger.log_message(f"Error during execution: {str(e)}")
                continue  # Continue with next data set even if current one fails