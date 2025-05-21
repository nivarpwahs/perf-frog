from locust import task, SequentialTaskSet, events
import json
import os
import yaml
import uuid

from utils.build_headers import build_common_headers
from utils.log_helper import Logger
from utils.data_loader import DataLoader


class JfrogOperations(SequentialTaskSet):
    header = build_common_headers()
    repo_name = None
    _test_stopped = False  # Class variable to track if test has been stopped
    wait_time = 1  # Fixed wait time between tasks
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate a unique ID for this task instance
        self.task_id = str(uuid.uuid4())[:8]
        # Load API configuration
        config_path = os.path.join(os.getcwd(), 'config', 'api_config.yml')
        with open(config_path, 'r') as f:
            self.api_config = yaml.safe_load(f)
        # Get data for this user at initialization
        try:
            self.test_data = DataLoader.get_data()
            self.repo_name = self.test_data['repo_name']
            Logger.log_message(f"Task {self.task_id} got data: {self.repo_name}")
        except IndexError:
            if not JfrogOperations._test_stopped:
                Logger.log_message("All test data has been used. Stopping test.")
                JfrogOperations._test_stopped = True
                self.user.environment.runner.quit()

    def on_start(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return
            
        # Check if we have any data to start with
        if not DataLoader.data_list:
            Logger.log_message("No test data available. Stopping test.")
            JfrogOperations._test_stopped = True
            self.user.environment.runner.quit()
            return

    @task
    def create_repo(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            Logger.log_message(f"Task {self.task_id} has no repository to create")
            return
        
        # Read create repository template
        template_path = os.path.join(os.getcwd(), 'requests', 'create_repository.json')
        with open(template_path, 'r') as f:
            request_body = json.load(f)
        
        # Replace placeholder with actual repo name
        request_body['key'] = self.repo_name
        
        # Make the request to create repository
        endpoint = self.api_config['endpoints']['create_repository']
        # Include repo name in the path
        path = f"{endpoint['path']}/{self.repo_name}"
        
        with self.client.put(
            path,
            json=request_body,
            headers=self.header,
            catch_response=True
        ) as response:
            if response.status_code == 201:
                Logger.log_message(f"Task {self.task_id} successfully created repository: {self.repo_name}")
            else:
                response.failure(f"Failed to create repository: {response.text}")
                Logger.log_message(f"Task {self.task_id} failed to create repository: {response.text}")

    @task
    def validate_repo(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            Logger.log_message(f"Task {self.task_id} has no repository to validate")
            return

        endpoint = self.api_config['endpoints']['check_repository']
        with self.client.get(
            endpoint['path'],
            headers=self.header,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                repositories = response.json()
                # Check if our created repository exists in the list
                repo_exists = any(repo['key'] == self.repo_name for repo in repositories)
                
                if repo_exists:
                    Logger.log_message(f"Task {self.task_id} successfully validated repository: {self.repo_name}")
                else:
                    response.failure(f"Repository {self.repo_name} not found in the list")
                    Logger.log_message(f"Task {self.task_id} failed to validate repository: {self.repo_name}")
            else:
                response.failure(f"Failed to get repositories list: {response.text}")
                Logger.log_message(f"Task {self.task_id} failed to get repositories list: {response.text}")

    def run(self):
        """Override run method to ensure tasks are executed in sequence"""
        while not JfrogOperations._test_stopped:
            for task in self.tasks:
                task(self).run()
                if JfrogOperations._test_stopped:
                    break
