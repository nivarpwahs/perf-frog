import json
import pytz
from influxdb import InfluxDBClient
from locust import events
import socket
import datetime
import psutil
from utils.log_helper import Logger


class EventInfluxHandlers:
    hostname = socket.gethostname()
    database_name = "locustdb"
    table_name = "REST_Table"
    
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
    def get_cpu_usage():
        return psutil.cpu_percent(interval=1)

    @staticmethod
    @events.request.add_listener
    def request_handler(request_type, name, response_time, response_length, response, exception, **kwargs):
        try:
            cpu_usage = EventInfluxHandlers.get_cpu_usage()
            
            if exception:
                failure_temp = {
                    "measurement": EventInfluxHandlers.table_name,
                    "tags": {
                        "hostname": EventInfluxHandlers.hostname,
                        "requestName": name,
                        "requestType": request_type,
                        "status": "FAIL",
                        "exception": str(exception).replace('"', '\\"')
                    },
                    "time": datetime.datetime.now(tz=pytz.UTC).isoformat(),
                    "fields": {
                        "responseTime": response_time,
                        "cpuUsage": cpu_usage
                    }
                }
                EventInfluxHandlers.influx_client.write_points([failure_temp])
            else:
                success_temp = {
                    "measurement": EventInfluxHandlers.table_name,
                    "tags": {
                        "hostname": EventInfluxHandlers.hostname,
                        "requestName": name,
                        "requestType": request_type,
                        "status": "PASS"
                    },
                    "time": datetime.datetime.now(tz=pytz.UTC).isoformat(),
                    "fields": {
                        "responseTime": response_time,
                        "cpuUsage": cpu_usage
                    }
                }
                EventInfluxHandlers.influx_client.write_points([success_temp])
        except Exception as e:
            Logger.log_message(f"Error writing to InfluxDB: {str(e)}")

    @staticmethod
    def write_custom_metric(measurement, tags, fields):
        try:
            cpu_usage = EventInfluxHandlers.get_cpu_usage()
            point = {
                "measurement": measurement,
                "tags": {
                    "hostname": EventInfluxHandlers.hostname,
                    **tags
                },
                "time": datetime.datetime.now(tz=pytz.UTC).isoformat(),
                "fields": {
                    **fields,
                    "cpuUsage": cpu_usage
                }
            }
            EventInfluxHandlers.influx_client.write_points([point])
        except Exception as e:
            Logger.log_message(f"Error writing custom metric to InfluxDB: {str(e)}")




