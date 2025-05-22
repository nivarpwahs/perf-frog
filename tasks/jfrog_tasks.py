from locust import task, SequentialTaskSet, events, between
import json
import os
import yaml
import uuid
import subprocess
import base64

from utils.build_headers import build_common_headers
from utils.log_helper import Logger
from utils.data_loader import DataLoader


class JfrogOperations(SequentialTaskSet):
    header = build_common_headers()
    repo_name = None
    policy_name = None
    watch_name = None
    _test_stopped = False  # Class variable to track if test has been stopped
    wait_time = between(1, 2)  # Wait between 1 and 2 seconds between tasks
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate a unique ID for this task instance
        self.task_id = str(uuid.uuid4())[:8]
        # Load API configuration
        config_path = os.path.join(os.getcwd(), 'config', 'api_config.yml')
        with open(config_path, 'r') as f:
            self.api_config = yaml.safe_load(f)
        # Load credentials
        creds_path = os.path.join(os.getcwd(), 'config', 'creds.yml')
        with open(creds_path, 'r') as f:
            self.creds = yaml.safe_load(f)

    def on_start(self):
        """Initialize when taskset starts"""
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return
            
        # Use the test data passed from the user
        if hasattr(self.user, 'test_data'):
            self.test_data = self.user.test_data
            self.repo_name = self.test_data['repo_name']
            self.policy_name = self.test_data['policy_name']
            self.watch_name = self.test_data['watch_name']
            Logger.log_message(f"Task {self.task_id} using data: {self.repo_name}")
        else:
            Logger.log_message("No test data available. Stopping test.")
            JfrogOperations._test_stopped = True
            self.user.environment.runner.quit()
            return

    @task
    def execute_sequence(self):
        """Execute all operations in sequence"""
        if JfrogOperations._test_stopped:
            return

        try:
            # Execute tasks in sequence
            self.create_repo()
            self.validate_repo()
            self.push_image()
            self.create_security_policy()
            self.create_watch()
            self.apply_watch()
            self.check_scan_status()
            self.verify_violations()
            
            # After successful execution, stop this taskset
            self.interrupt()
            
        except Exception as e:
            Logger.log_message(f"Error in task sequence: {str(e)}")
            # Don't re-raise the exception, let the user continue with next data set
            self.interrupt()

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
            if "Successfully created repository" in response.text:
                Logger.log_message(f"Task {self.task_id} successfully created repository: {self.repo_name}")
                response.success()
            elif "repository key already exists" in response.text:
                Logger.log_message(f"Task {self.task_id} repository already exists: {self.repo_name}")
                response.success()  # Mark as success since this is an expected case
            else:
                error_msg = f"Failed to create repository: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)

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
                    response.success()
                else:
                    error_msg = f"Repository {self.repo_name} not found in the list"
                    Logger.log_message(f"Task {self.task_id} {error_msg}")
                    response.failure(error_msg)
            else:
                error_msg = f"Failed to get repositories list: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)

    @task
    def push_image(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            Logger.log_message(f"Task {self.task_id} has no repository to push image to")
            return

        try:
            # Extract hostname without https
            hostname = self.api_config['base_url'].replace('https://', '')
            Logger.log_message(f"Task {self.task_id} using hostname: {hostname}")
            
            # Decode auth token to get username and password
            auth_token = self.creds['auth_token']
            decoded_token = base64.b64decode(auth_token).decode('utf-8')
            username, password = decoded_token.split(':')
            Logger.log_message(f"Task {self.task_id} decoded credentials for user: {username}")

            # Use the specific Docker path for macOS
            docker_path = '/Applications/Docker.app/Contents/Resources/bin/docker'
            if not os.path.exists(docker_path):
                error_msg = f"Docker not found at {docker_path}. Please ensure Docker is installed"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                return False
            
            Logger.log_message(f"Task {self.task_id} using Docker at: {docker_path}")

            # Verify Docker is running
            check_docker = subprocess.run([docker_path, 'info'], capture_output=True, text=True)
            if check_docker.returncode != 0:
                error_msg = f"Docker is not running or not accessible: {check_docker.stderr}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                return False
            
            Logger.log_message(f"Task {self.task_id} Docker is running and accessible")

            # Create temporary Docker config directory
            temp_dir = os.path.join(os.getcwd(), 'temp_docker_config')
            os.makedirs(temp_dir, exist_ok=True)
            config_path = os.path.join(temp_dir, 'config.json')

            # Create Docker config with credentials
            config = {
                "auths": {
                    hostname: {
                        "auth": base64.b64encode(f"{username}:{password}".encode()).decode()
                    }
                }
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f)

            # Set DOCKER_CONFIG environment variable
            env = os.environ.copy()
            env['DOCKER_CONFIG'] = temp_dir

            # Pull Alpine image
            pull_cmd = [docker_path, 'pull', 'alpine:3.9']
            Logger.log_message(f"Task {self.task_id} executing command: {' '.join(pull_cmd)}")
            pull_result = subprocess.run(pull_cmd, capture_output=True, text=True, env=env)
            if pull_result.returncode != 0:
                error_msg = f"Failed to pull Alpine image: {pull_result.stderr}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                return False
            Logger.log_message(f"Task {self.task_id} command output: {pull_result.stdout}")

            # Tag the image
            tag_cmd = [docker_path, 'tag', 'alpine:3.9', f'{hostname}/{self.repo_name}/test01:test01']
            Logger.log_message(f"Task {self.task_id} executing command: {' '.join(tag_cmd)}")
            tag_result = subprocess.run(tag_cmd, capture_output=True, text=True, env=env)
            if tag_result.returncode != 0:
                error_msg = f"Failed to tag image: {tag_result.stderr}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                return False
            Logger.log_message(f"Task {self.task_id} successfully tagged image")

            # Push the image
            push_cmd = [docker_path, 'push', f'{hostname}/{self.repo_name}/test01:test01']
            Logger.log_message(f"Task {self.task_id} executing command: {' '.join(push_cmd)}")
            push_result = subprocess.run(push_cmd, capture_output=True, text=True, env=env)
            if push_result.returncode != 0:
                error_msg = f"Failed to push image: {push_result.stderr}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                return False
            Logger.log_message(f"Task {self.task_id} command output: {push_result.stdout}")

            # Clean up temporary config
            try:
                os.remove(config_path)
                os.rmdir(temp_dir)
            except Exception as e:
                Logger.log_message(f"Task {self.task_id} Warning: Failed to clean up temporary Docker config: {str(e)}")

            Logger.log_message(f"Task {self.task_id} successfully pushed image to repository: {self.repo_name}")
            return True

        except Exception as e:
            error_msg = f"Failed to push image: {str(e)}"
            Logger.log_message(f"Task {self.task_id} {error_msg}")
            return False

    @task
    def create_security_policy(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.policy_name:
            Logger.log_message(f"Task {self.task_id} has no policy name to create")
            return

        # Read create policy template
        template_path = os.path.join(os.getcwd(), 'requests', 'create_policy.json')
        with open(template_path, 'r') as f:
            request_body = json.load(f)
        
        # Replace placeholder with actual policy name
        request_body['name'] = self.policy_name
        
        # Make the request to create policy
        endpoint = self.api_config['endpoints']['create_policy']
        with self.client.post(
            endpoint['path'],
            json=request_body,
            headers=self.header,
            catch_response=True
        ) as response:
            response_data = response.json()
            if "Policy created successfully" in response_data.get('info', ''):
                Logger.log_message(f"Task {self.task_id} successfully created policy: {self.policy_name}")
                response.success()
            elif "Policy already exists" in response.text:
                Logger.log_message(f"Task {self.task_id} policy already exists: {self.policy_name}")
                response.success()  # Mark as success since this is an expected case
            else:
                error_msg = f"Failed to create policy: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)

    @task
    def create_watch(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.watch_name or not self.repo_name or not self.policy_name:
            Logger.log_message(f"Task {self.task_id} missing required data for watch creation")
            return

        # Read create watch template
        template_path = os.path.join(os.getcwd(), 'requests', 'create_watch.json')
        with open(template_path, 'r') as f:
            request_body = json.load(f)
        
        # Replace placeholders with actual values
        request_body['general_data']['name'] = self.watch_name
        request_body['project_resources']['resources'][0]['name'] = self.repo_name
        request_body['assigned_policies'][0]['name'] = self.policy_name
        
        # Make the request to create watch
        endpoint = self.api_config['endpoints']['create_watch']
        with self.client.post(
            endpoint['path'],
            json=request_body,
            headers=self.header,
            catch_response=True
        ) as response:
            if "Watch has been successfully created" in response.text:
                Logger.log_message(f"Task {self.task_id} successfully created watch: {self.watch_name}")
                response.success()
            elif "Watch already exists" in response.text:
                Logger.log_message(f"Task {self.task_id} watch already exists: {self.watch_name}")
                response.success()  # Mark as success since this is an expected case
            else:
                error_msg = f"Failed to create watch: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)

    @task
    def apply_watch(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.watch_name:
            Logger.log_message(f"Task {self.task_id} has no watch to apply")
            return

        # Read apply watch template
        template_path = os.path.join(os.getcwd(), 'requests', 'apply_watch.json')
        with open(template_path, 'r') as f:
            request_body = json.load(f)
        
        # Replace placeholder with actual watch name
        request_body['watch_names'] = [self.watch_name]
        
        # Make the request to apply watch
        endpoint = self.api_config['endpoints']['apply_watch']
        with self.client.post(
            endpoint['path'],
            json=request_body,
            headers=self.header,
            catch_response=True
        ) as response:
            if "History Scan is in progress" in response.text:
                Logger.log_message(f"Task {self.task_id} successfully started watch scan: {self.watch_name}")
                response.success()
            else:
                error_msg = f"Failed to apply watch: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)

    @task
    def check_scan_status(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            Logger.log_message(f"Task {self.task_id} has no repository to check scan status")
            return

        # Read check scan status template
        template_path = os.path.join(os.getcwd(), 'requests', 'check_scan_status.json')
        with open(template_path, 'r') as f:
            request_body = json.load(f)
        
        # Replace placeholder with actual repo name
        request_body['repo'] = self.repo_name
        
        # Make the request to check scan status
        endpoint = self.api_config['endpoints']['check_scan_status']
        with self.client.post(
            endpoint['path'],
            json=request_body,
            headers=self.header,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                status_data = response.json()
                if status_data.get('overall', {}).get('status') == 'DONE':
                    Logger.log_message(f"Task {self.task_id} scan completed for repository: {self.repo_name}")
                    response.success()
                else:
                    Logger.log_message(f"Task {self.task_id} scan in progress for repository: {self.repo_name}")
                    response.success()
            else:
                error_msg = f"Failed to check scan status: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)

    @task
    def verify_violations(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.watch_name or not self.repo_name:
            Logger.log_message(f"Task {self.task_id} missing required data for violation verification")
            return

        # Read verify violations template
        template_path = os.path.join(os.getcwd(), 'requests', 'verify_violations.json')
        with open(template_path, 'r') as f:
            request_body = json.load(f)
        
        # Replace placeholders with actual values
        request_body['filters']['watch_name'] = self.watch_name
        request_body['filters']['resources']['artifacts'][0]['repo'] = self.repo_name
        
        # Make the request to verify violations
        endpoint = self.api_config['endpoints']['verify_violations']
        with self.client.post(
            endpoint['path'],
            json=request_body,
            headers=self.header,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                violations_data = response.json()
                total_violations = violations_data.get('total_violations', 0)
                Logger.log_message(f"Task {self.task_id} found {total_violations} violations for watch: {self.watch_name}")
                response.success()
            else:
                error_msg = f"Failed to verify violations: {response.text}"
                Logger.log_message(f"Task {self.task_id} {error_msg}")
                response.failure(error_msg)
