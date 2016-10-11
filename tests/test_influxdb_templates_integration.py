# -*- coding: utf-8 -*-
import os
import unittest
from influxdb import InfluxDBClient
import influxdb.exceptions
import graphite_influxdb
import graphite_influxdb.utils
from graphite_influxdb.utils import Query
from graphite_influxdb.constants import SERIES_LOADER_MUTEX_KEY, \
     MEMCACHE_SERIES_DEFAULT_TTL, LOADER_LIMIT
import datetime
import time
try:
    import memcache
except ImportError:
    pass
import sys

os.environ['TZ'] = 'UTC'

class InfluxGraphTemplatesIntegrationTestCase(unittest.TestCase):
    """Test node lookup and data retrieval when using tags on and Graphite
    templates configured on InfluxGraph"""
    
    def setUp(self):
        self.metric_prefix = "template_integration_test"
        self.tags = {
            'a_test_type': self.metric_prefix,
            'b_host': 'localhost',
            'env': 'int',
            'region': 'the_west',
            }
        self.measurements = ['cpu', 'memory', 'load', 'iops']
        self.graphite_series = ["%s.%s" % (self.metric_prefix, ".".join(
            self.tags.values() + [m])) for m in self.measurements]
        # 
        # import ipdb; ipdb.set_trace()
        self.step, self.num_datapoints, self.db_name = 60, 2, 'integration_test'
        self.start_time, self.end_time = (datetime.datetime.utcnow() - datetime.timedelta(hours=1)), \
          datetime.datetime.utcnow()
        self.steps = int(round((int(self.end_time.strftime("%s")) - \
                                int(self.start_time.strftime("%s"))) * 1.0 / self.step)) + 1
        self.config = { 'influxdb': {
            'host' : 'localhost',
            'port' : 8086,
            'user' : 'root',
            'pass' : 'root',
            'db' : self.db_name,
            'log_level' : 'debug',
            'templates' : [
                "%s type.host.measurement* env=int,region=the_west" % (self.metric_prefix,)
                ],
            },
            # 'search_index': 'index',
        }
        self.client = InfluxDBClient(database=self.db_name)
        self.default_nodes_limit = LOADER_LIMIT
        self.setup_db()
        self.finder = graphite_influxdb.InfluxdbFinder(self.config)

    def setup_db(self):
        try:
            self.client.drop_database(self.db_name)
        except influxdb.exceptions.InfluxDBClientError:
            pass
        self.client.create_database(self.db_name)
        data = [{
            "measurement": measurement,
            "tags": self.tags,
            "time": _time,
            "fields": {
                "value": 1,
                }
            }
            for measurement in self.measurements
            for _time in [
                (self.end_time - datetime.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                (self.end_time - datetime.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ]]
        self.assertTrue(self.client.write_points(data))

    def tearDown(self):
        self.client.drop_database(self.db_name)

    def test_templated_index_find(self):
        query = Query('*')
        nodes = [n.path for n in self.finder.find_nodes(query)]
        expected = [self.metric_prefix]
        self.assertEqual(nodes, expected,
                         msg="Got root branch query result %s - wanted %s" % (
                             nodes, expected,))
        query = Query("%s.*" % (self.metric_prefix,))
        nodes = [n.path for n in self.finder.find_nodes(query)]
        expected = [".".join(list(set([d for e in [
            m.split('.')[0:2] for m in self.graphite_series] for d in e])))]
        self.assertEqual(nodes, expected,
                         msg="Got root branch query result %s - wanted %s" % (
                             nodes, expected,))
        # TODO - figure out how to handle default tags
        query = Query("%s.%s.*" % (self.metric_prefix, self.tags['b_host']))
        nodes = [n.path for n in self.finder.find_nodes(query)]
        expected = self.measurements
        self.assertEqual(nodes, expected,
                         msg="Got root branch query result %s - wanted %s" % (
                             nodes, expected,))

    def test_templated_data_query(self):
        serie = 'template_integration_test.localhost.int.the_west.cpu'
        # serie = self.graphite_series[0]
        nodes = list(self.finder.find_nodes(Query(serie)))
        # 1/0
        time_info, data = self.finder.fetch_multi(nodes,
                                                  int(self.start_time.strftime("%s")),
                                                  int(self.end_time.strftime("%s")))
        self.assertTrue(serie in data,
                        msg="Did not get data for requested series %s - got data for %s" % (
                            serie, data.keys(),))
        self.assertEqual(time_info,
                         (int(self.start_time.strftime("%s")),
                          int(self.end_time.strftime("%s")),
                         self.step),
                         msg="Time info and step do not match our requested values")
        datapoints = [v for v in data[serie] if v]
        self.assertTrue(len(datapoints) == self.num_datapoints,
                        msg="Expected %s datapoints - got %s" % (
                            self.num_datapoints, len(datapoints),))

if __name__ == '__main__':
    unittest.main()