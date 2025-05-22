from locust import task, SequentialTaskSet, events, between
import json
import os
import yaml
import uuid
import subprocess
import base64
import time

from utils.build_headers import build_common_headers
from utils.log_helper import Logger
from utils.data_loader import DataLoader
from utils.influxdb_client import EventInfluxHandlers


class JfrogOperations(SequentialTaskSet):
    header = build_common_headers()
    repo_name = None
    policy_name = None
    watch_name = None
    _test_stopped = False
    wait_time = between(1, 2)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = str(uuid.uuid4())[:8]
        config_path = os.path.join(os.getcwd(), 'config', 'api_config.yml')
        with open(config_path, 'r') as f:
            self.api_config = yaml.safe_load(f)
        creds_path = os.path.join(os.getcwd(), 'config', 'creds.yml')
        with open(creds_path, 'r') as f:
            self.creds = yaml.safe_load(f)

    def on_start(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return
            
        if hasattr(self.user, 'test_data'):
            self.test_data = self.user.test_data
            self.repo_name = self.test_data['repo_name']
            self.policy_name = self.test_data['policy_name']
            self.watch_name = self.test_data['watch_name']
        else:
            JfrogOperations._test_stopped = True
            self.user.environment.runner.quit()
            return

    def record_operation_metric(self, operation_name, status, duration, additional_fields=None):
        fields = {
            "duration": duration,
            "status": 1 if status else 0
        }
        if additional_fields:
            fields.update(additional_fields)
            
        EventInfluxHandlers.write_custom_metric(
            "jfrog_operations",
            {
                "task_id": self.task_id,
                "operation": operation_name,
                "repo_name": self.repo_name
            },
            fields
        )

    @task
    def execute_sequence(self):
        if JfrogOperations._test_stopped:
            return

        try:
            self.create_repo()
            self.validate_repo()
            self.push_image()
            self.create_security_policy()
            self.create_watch()
            self.apply_watch()
            self.check_scan_status()
            self.verify_violations()
            self.interrupt()
        except Exception as e:
            self.interrupt()

    @task
    def create_repo(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            return
        
        start_time = time.time()
        success = False
        
        try:
            template_path = os.path.join(os.getcwd(), 'requests', 'create_repository.json')
            with open(template_path, 'r') as f:
                request_body = json.load(f)
            
            request_body['key'] = self.repo_name
            endpoint = self.api_config['endpoints']['create_repository']
            path = f"{endpoint['path']}/{self.repo_name}"
            
            with self.client.put(
                path,
                json=request_body,
                headers=self.header,
                catch_response=True
            ) as response:
                if "Successfully created repository" in response.text or "repository key already exists" in response.text:
                    response.success()
                    success = True
                else:
                    response.failure(response.text)
        except Exception as e:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("create_repo", success, duration)

    @task
    def validate_repo(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            return

        start_time = time.time()
        success = False
        
        try:
            endpoint = self.api_config['endpoints']['check_repository']
            with self.client.get(
                endpoint['path'],
                headers=self.header,
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    repositories = response.json()
                    repo_exists = any(repo['key'] == self.repo_name for repo in repositories)
                    if repo_exists:
                        response.success()
                        success = True
                    else:
                        response.failure(f"Repository {self.repo_name} not found")
                else:
                    response.failure(response.text)
        except Exception as e:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("validate_repo", success, duration)

    @task
    def push_image(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            return

        start_time = time.time()
        success = False
        image_size = 0
        
        try:
            hostname = self.api_config['base_url'].replace('https://', '')
            auth_token = self.creds['auth_token']
            decoded_token = base64.b64decode(auth_token).decode('utf-8')
            username, password = decoded_token.split(':')

            docker_path = '/Applications/Docker.app/Contents/Resources/bin/docker'
            if not os.path.exists(docker_path):
                return False

            check_docker = subprocess.run([docker_path, 'info'], capture_output=True, text=True)
            if check_docker.returncode != 0:
                return False

            temp_dir = os.path.join(os.getcwd(), 'temp_docker_config')
            os.makedirs(temp_dir, exist_ok=True)
            config_path = os.path.join(temp_dir, 'config.json')

            config = {
                "auths": {
                    hostname: {
                        "auth": base64.b64encode(f"{username}:{password}".encode()).decode()
                    }
                }
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f)

            env = os.environ.copy()
            env['DOCKER_CONFIG'] = temp_dir

            pull_cmd = [docker_path, 'pull', 'alpine:3.9']
            pull_result = subprocess.run(pull_cmd, capture_output=True, text=True, env=env)
            if pull_result.returncode != 0:
                return False

            inspect_cmd = [docker_path, 'inspect', 'alpine:3.9', '--format', '{{.Size}}']
            size_result = subprocess.run(inspect_cmd, capture_output=True, text=True)
            if size_result.returncode == 0:
                image_size = int(size_result.stdout.strip())

            tag_cmd = [docker_path, 'tag', 'alpine:3.9', f'{hostname}/{self.repo_name}/test01:test01']
            tag_result = subprocess.run(tag_cmd, capture_output=True, text=True, env=env)
            if tag_result.returncode != 0:
                return False

            push_cmd = [docker_path, 'push', f'{hostname}/{self.repo_name}/test01:test01']
            push_result = subprocess.run(push_cmd, capture_output=True, text=True, env=env)
            if push_result.returncode != 0:
                return False

            try:
                os.remove(config_path)
                os.rmdir(temp_dir)
            except Exception:
                pass

            success = True

        except Exception:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("push_image", success, duration, {"image_size": image_size})

    @task
    def create_security_policy(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.policy_name:
            return

        start_time = time.time()
        success = False
        
        try:
            template_path = os.path.join(os.getcwd(), 'requests', 'create_policy.json')
            with open(template_path, 'r') as f:
                request_body = json.load(f)
            
            request_body['name'] = self.policy_name
            endpoint = self.api_config['endpoints']['create_policy']
            with self.client.post(
                endpoint['path'],
                json=request_body,
                headers=self.header,
                catch_response=True
            ) as response:
                response_data = response.json()
                if "Policy created successfully" in response_data.get('info', '') or "Policy already exists" in response.text:
                    response.success()
                    success = True
                else:
                    response.failure(response.text)
        except Exception:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("create_policy", success, duration)

    @task
    def create_watch(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.watch_name or not self.repo_name or not self.policy_name:
            return

        start_time = time.time()
        success = False
        
        try:
            template_path = os.path.join(os.getcwd(), 'requests', 'create_watch.json')
            with open(template_path, 'r') as f:
                request_body = json.load(f)
            
            request_body['general_data']['name'] = self.watch_name
            request_body['project_resources']['resources'][0]['name'] = self.repo_name
            request_body['assigned_policies'][0]['name'] = self.policy_name
            
            endpoint = self.api_config['endpoints']['create_watch']
            with self.client.post(
                endpoint['path'],
                json=request_body,
                headers=self.header,
                catch_response=True
            ) as response:
                if "Watch has been successfully created" in response.text or "Watch already exists" in response.text:
                    response.success()
                    success = True
                else:
                    response.failure(response.text)
        except Exception:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("create_watch", success, duration)

    @task
    def apply_watch(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.watch_name:
            return

        start_time = time.time()
        success = False
        
        try:
            template_path = os.path.join(os.getcwd(), 'requests', 'apply_watch.json')
            with open(template_path, 'r') as f:
                request_body = json.load(f)
            
            request_body['watch_names'] = [self.watch_name]
            endpoint = self.api_config['endpoints']['apply_watch']
            with self.client.post(
                endpoint['path'],
                json=request_body,
                headers=self.header,
                catch_response=True
            ) as response:
                if "History Scan is in progress" in response.text:
                    response.success()
                    success = True
                else:
                    response.failure(response.text)
        except Exception:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("apply_watch", success, duration)

    @task
    def check_scan_status(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.repo_name:
            return

        start_time = time.time()
        success = False
        scan_status = "UNKNOWN"
        
        try:
            template_path = os.path.join(os.getcwd(), 'requests', 'check_scan_status.json')
            with open(template_path, 'r') as f:
                request_body = json.load(f)
            
            request_body['repo'] = self.repo_name
            endpoint = self.api_config['endpoints']['check_scan_status']
            with self.client.post(
                endpoint['path'],
                json=request_body,
                headers=self.header,
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    status_data = response.json()
                    scan_status = status_data.get('overall', {}).get('status', 'UNKNOWN')
                    response.success()
                    success = True
                else:
                    response.failure(response.text)
        except Exception:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("check_scan_status", success, duration, {"scan_status": scan_status})

    @task
    def verify_violations(self):
        if JfrogOperations._test_stopped:
            self.user.environment.runner.quit()
            return

        if not self.watch_name or not self.repo_name:
            return

        start_time = time.time()
        success = False
        total_violations = 0
        
        try:
            template_path = os.path.join(os.getcwd(), 'requests', 'verify_violations.json')
            with open(template_path, 'r') as f:
                request_body = json.load(f)
            
            request_body['filters']['watch_name'] = self.watch_name
            request_body['filters']['resources']['artifacts'][0]['repo'] = self.repo_name
            
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
                    response.success()
                    success = True
                else:
                    response.failure(response.text)
        except Exception:
            success = False
            
        duration = time.time() - start_time
        self.record_operation_metric("verify_violations", success, duration, {"total_violations": total_violations})
