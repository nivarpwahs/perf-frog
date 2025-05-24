import json
import pytz
from influxdb import InfluxDBClient
from locust import events
import socket
import datetime
from utils.log_helper import Logger
from collections import defaultdict
import time


class EventInfluxHandlers:
    hostname = socket.gethostname()
    database_name = "locustdb"
    table_name = "REST_Table"
    
    # Track metrics for percentiles
    response_times = defaultdict(list)
    last_cleanup = time.time()
    cleanup_interval = 300  # 5 minutes
    
    influx_client = InfluxDBClient(
        host='localhost',
        port=8086,
        database=database_name,
        username='admin',
        password='admin123'
    )

    @staticmethod
    def init_influx_client():
        try:
            EventInfluxHandlers.influx_client.drop_database(EventInfluxHandlers.database_name)
            EventInfluxHandlers.influx_client.create_database(EventInfluxHandlers.database_name)
            EventInfluxHandlers.influx_client.switch_database(EventInfluxHandlers.database_name)
        except Exception as e:
            Logger.log_message(f"Error initializing InfluxDB client: {str(e)}")

    @staticmethod
    def calculate_percentiles(response_times_list, percentiles=[95, 99]):
        if not response_times_list:
            return {f"p{p}": 0 for p in percentiles}
        
        sorted_times = sorted(response_times_list)
        result = {}
        for p in percentiles:
            index = int(len(sorted_times) * p / 100)
            result[f"p{p}"] = sorted_times[index]
        return result

    @staticmethod
    def cleanup_old_metrics():
        current_time = time.time()
        if current_time - EventInfluxHandlers.last_cleanup > EventInfluxHandlers.cleanup_interval:
            for api_name in list(EventInfluxHandlers.response_times.keys()):
                # Keep only last 5 minutes of data for percentiles
                cutoff_time = current_time - 300
                EventInfluxHandlers.response_times[api_name] = [
                    rt for rt in EventInfluxHandlers.response_times[api_name]
                    if rt['timestamp'] > cutoff_time
                ]
            EventInfluxHandlers.last_cleanup = current_time

    @staticmethod
    @events.request.add_listener
    def request_handler(request_type, name, response_time, response_length, response, exception, **kwargs):
        try:
            current_time = time.time()
            
            # Track response time for percentiles
            EventInfluxHandlers.response_times[name].append({
                'timestamp': current_time,
                'response_time': response_time
            })
            
            # Cleanup old metrics periodically
            EventInfluxHandlers.cleanup_old_metrics()
            
            # Calculate percentiles
            response_times_list = [rt['response_time'] for rt in EventInfluxHandlers.response_times[name]]
            percentiles = EventInfluxHandlers.calculate_percentiles(response_times_list)
            
            # Determine status code category
            status_category = "UNKNOWN"
            if response:
                status_code = response.status_code
                if 200 <= status_code < 300:
                    status_category = "2xx"
                elif 400 <= status_code < 500:
                    status_category = "4xx"
                elif 500 <= status_code < 600:
                    status_category = "5xx"
            
            # Prepare base tags
            base_tags = {
                "requestName": name,
                "status_category": status_category
            }
            
            # Prepare base fields
            base_fields = {
                "p95": percentiles.get("p95", 0),
                "p99": percentiles.get("p99", 0),
                "throughput": 1,  # Each request contributes 1 to throughput
                "error": 1 if exception else 0
            }
            
            point = {
                "measurement": EventInfluxHandlers.table_name,
                "tags": base_tags,
                "time": datetime.datetime.now(tz=pytz.UTC).isoformat(),
                "fields": base_fields
            }
            
            EventInfluxHandlers.influx_client.write_points([point])
            
        except Exception as e:
            Logger.log_message(f"Error writing to InfluxDB: {str(e)}")

    @staticmethod
    def write_custom_metric(measurement, tags, fields):
        try:
            point = {
                "measurement": measurement,
                "tags": tags,
                "time": datetime.datetime.now(tz=pytz.UTC).isoformat(),
                "fields": fields
            }
            EventInfluxHandlers.influx_client.write_points([point])
        except Exception as e:
            Logger.log_message(f"Error writing custom metric to InfluxDB: {str(e)}")




