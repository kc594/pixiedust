# -------------------------------------------------------------------------------
# Copyright IBM Corp. 2016
# 
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
# http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# -------------------------------------------------------------------------------
from six import iteritems
from pyspark.sql.types import *
import pixiedust
from pixiedust.utils.shellAccess import ShellAccess
from pixiedust.utils.template import PixiedustTemplateEnvironment
import uuid
import tempfile
from collections import OrderedDict
from IPython.display import display, HTML, Javascript
try:
    from urllib.request import Request, urlopen, URLError, HTTPError
except ImportError:
    from urllib2 import Request, urlopen, URLError, HTTPError

dataDefs = OrderedDict([
    ("1", {
        "displayName": "Car performance data", 
        "url": "https://apsportal.ibm.com/exchange-api/v1/entries/c81e9be8daf6941023b9dc86f303053b/data?accessKey=21818d62c8eee8fb329cc401ea263033",
        "topic": "transportation",
        "publisher": "IBM",
        "schema2": [('mpg','int'),('cylinders','int'),('engine','double'),('horsepower','int'),('weight','int'),
            ('acceleration','double'),('year','int'),('origin','string'),('name','string')]
    }),
    ("2", {
        "displayName": "Airbnb Data for Analytics: Washington D.C. Listings", 
        "url": "https://apsportal.ibm.com/exchange-api/v1/entries/c3af8034bd7f7374f87b3df6420865d5/data?accessKey=693121eff3eb97c917c5ac9987ee3095",
        "topic": "Economy & Business",
        "publisher": "IBM Cloud Data Services"
    })
])

def sampleData(dataId=None):
    global dataDefs
    return SampleData(dataDefs).sampleData(dataId)

class SampleData(object):
    env = PixiedustTemplateEnvironment()
    def __init__(self, dataDefs):
        self.dataDefs = dataDefs

    def sampleData(self, dataId = None):
        if dataId is None:
            self.printSampleDataList()            
        elif str(dataId) in dataDefs:
            return self.loadSparkDataFrameFromSampleData(dataDefs[str(dataId)])
        else:
            print("Unknown sample data identifier. Please choose an id from the list below")
            self.printSampleDataList()

    def printSampleDataList(self):
        display( HTML( self.env.getTemplate("sampleData.html").render( dataDefs = iteritems(self.dataDefs) ) ))
        #for key, val in iteritems(self.dataDefs):
        #    print("{0}: {1}".format(key, val["displayName"]))

    def dataLoader(self, path, schema=None):
        #TODO: if in Spark 2.0 or higher, use new API to load CSV
        load = ShellAccess["sqlContext"].read.format('com.databricks.spark.csv')
        if schema is not None:
            def getType(t):
                if t == 'int':
                    return IntegerType()
                elif t == 'double':
                    return DoubleType()
                else:
                    return StringType()
            return load.options(header='true').load(path, schema=StructType([StructField(item[0], getType(item[1]), True) for item in schema]))
        else:
            return load.options(header='true', inferschema='true').load(path)

    def loadSparkDataFrameFromSampleData(self, dataDef):
        return Downloader(dataDef).download(self.dataLoader)

class Downloader(object):
    def __init__(self, dataDef):
        self.dataDef = dataDef
        self.headers = {"User-Agent": "PixieDust Sample Data Downloader/1.0"}
        self.prefix = str(uuid.uuid4())[:8]
    
    def download(self, dataLoader):
        url = self.dataDef["url"]
        displayName = self.dataDef["displayName"]
        req = Request(url, None, self.headers)
        print("Downloading '{0}' from {1}".format(displayName, url))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            self.write(urlopen(req), f)
            try:
                print("Creating pySpark DataFrame for '{0}'. Please wait...".format(displayName))
                return dataLoader(f.name, self.dataDef.get("schema", None))
            finally:
                print("Successfully created pySpark DataFrame for '{0}'".format(displayName))
            
    def report(self, bytes_so_far, chunk_size, total_size):
        if bytes_so_far == 0:
            display( HTML( """
                <div>
                    <span id="pm_label{0}">Starting download...</span>
                    <progress id="pm_progress{0}" max="100" value="0" style="width:200px"></progress>
                </div>""".format(self.prefix)
                )
            )
        else:
            percent = float(bytes_so_far) / total_size
            percent = round(percent*100, 2)
            display(
                Javascript("""
                    $("#pm_label{prefix}").text("{label}");
                    $("#pm_progress{prefix}").attr("value", {percent});
                """.format(prefix=self.prefix, label="Downloaded {0} of {1} bytes".format(bytes_so_far, total_size), percent=percent))
            )

    def write(self, response, file, chunk_size=8192):
        total_size = response.headers['Content-Length'].strip() if 'Content-Length' in response.headers else 100
        total_size = int(total_size)
        bytes_so_far = 0

        self.report(bytes_so_far, chunk_size, total_size)

        while 1:
            chunk = response.read(chunk_size)
            bytes_so_far += len(chunk)
            if not chunk:
                break
            file.write(chunk)             
            total_size = bytes_so_far if bytes_so_far > total_size else total_size
            self.report(bytes_so_far, chunk_size, total_size)

        return bytes_so_far