import json
import pytz
from influxdb import InfluxDBClient
from locust import events
import socket
import datetime


class EventInfluxHandlers:

    hostname = socket.gethostname()
    data_base_name = "locustdb"
    table_name = "REST_Table"

    influxDbClient = InfluxDBClient(host='localhost',
                                    port=8086,
                                    database=data_base_name)

    @staticmethod
    def init_influx_client():
        EventInfluxHandlers.influxDbClient.drop_database(EventInfluxHandlers.data_base_name)
        EventInfluxHandlers.influxDbClient.create_database(EventInfluxHandlers.data_base_name)
        EventInfluxHandlers.influxDbClient.switch_database(EventInfluxHandlers.data_base_name)

    @staticmethod
    @events.request.add_listener
    def request_handler(request_type, name, response_time, response_length, response, exception, **kwargs):
        try:
            if exception:
                # Handle failure
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
                        "responseLength": response_length
                    }
                }
                EventInfluxHandlers.influxDbClient.write_points([failure_temp])
            else:
                # Handle success
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
                        "responseLength": response_length
                    }
                }
                EventInfluxHandlers.influxDbClient.write_points([success_temp])
        except Exception as e:
            Logger.log_message(f"Error writing to InfluxDB: {str(e)}")




