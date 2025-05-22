## Overview

This project is a scalable, modular, and distributed performance testing framework using Locust. It is designed to simulate enterprise level application and provides robust analytics through InfluxDB and Grafana integration.

## Architecture

<img width="500" alt="image" src="https://github.com/user-attachments/assets/9dba6096-a2f7-4c06-8adf-84d3f7f755b9" />



## Steps To Setup

1. Install Python https://www.python.org/downloads/
2. Install Docker Desktop https://www.docker.com/products/docker-desktop/
3. Install Dependencies required `pip3 install <dependencies>` list of all the dependencies are present in the requirement.txt file. Alternatively one can execute the requirement.txt by running pip3 install -r requirement.txt
4. Start the docker Desktop
5. On Terminal perform the following steps to start influxdb and grafana execute 
docker run -d \                                          
  --name influxdb \
  --network monitoring \
  -p 8086:8086 \
  -e INFLUXDB_DB=locustdb \
  -e INFLUXDB_ADMIN_USER=admin \
  -e INFLUXDB_ADMIN_PASSWORD=admin123 \
  -v influxdb_data:/var/lib/influxdb \
  influxdb:1.8
6. docker pull grafana/grafana
7. docker run -d --name=grafana -p 3000:3000 grafana/grafana
8. Once the influxDB and grafana has started, open the grafana UI to setup INFLUXDB --- GRAFANA integration http://localhost:3000
9. Setup Dashboard by choosing influx datastore
10. select query language: influxql , Http url : http://influxdb:8086 , Databse: locustdb , user : admin , password : admin123 and save
11. open the code in Pycharm IDE and change the following things
12. host url : <your_env>.jfrog.io in api_config.yml, master_config.yml and base64 encoded username password in creds.yml
13. to encode go to any base64 encoding website and encode <username>:<password>


## Steps to Run

1. The test_data.csv contains test data related to repo_name, policy_name and watch_name which we will be needing for the APIs. For sanity load keep the data less and once the sanity is complete test data can be added as per load needs. The data can also be read via Amazons S3 which has the storage capacity.
2. Once the test data is setup there are 2 configs master_config.yml and slave_config.yml. This is used for distributed execution. Master delegates the execution tasks to workers. Read the config and change as per the load needs.
3. open 3 terminal on the project root, on one terminal execute master config `locust -f load_test.py --config config/master_config.yml` and on other 2 terminal execute the slave config `locust -f load_test.py --config config/slave_config.yml` 
4. Once both the workers are up and running the load generation will start, influxDB will get the dump data and can be visualised in Grafana for the metrics.


     




