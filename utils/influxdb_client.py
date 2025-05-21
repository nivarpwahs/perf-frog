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
        if exception:
            # Handle failure
            failure_temp = \
                '[{"measurement": "%s",\
                "tags": {\
                    "hostname": "%s",\
                    "requestName": "%s",\
                    "requestType": "%s",\
                    "status": "%s",\
                    "exception": "%s"\
                },\
                "time": "%s",\
                "fields": {\
                    "responseTime": "%s",\
                    "responseLength": "%s"\
                }\
             }]'

            json_string = failure_temp % (EventInfluxHandlers.table_name, EventInfluxHandlers.hostname, name, request_type,
                                          "FAIL", str(exception), datetime.datetime.now(tz=pytz.UTC),
                                          response_time, response_length)
        else:
            # Handle success
            success_temp = \
                '[{"measurement": "%s",\
                "tags": {\
                    "hostname": "%s",\
                    "requestName": "%s",\
                    "requestType": "%s",\
                    "status": "%s"\
                },\
                "time": "%s",\
                "fields": {\
                    "responseTime": "%s",\
                    "responseLength": "%s"\
                }\
             }]'

            json_string = success_temp % (EventInfluxHandlers.table_name, EventInfluxHandlers.hostname, name, request_type,
                                          "PASS", datetime.datetime.now(tz=pytz.UTC), response_time, response_length)
        
        EventInfluxHandlers.influxDbClient.write_points(json.loads(json_string))




