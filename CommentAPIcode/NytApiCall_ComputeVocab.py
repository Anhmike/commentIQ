# -*- coding: utf-8 -*-

# This code scrap the data from NYT API via the API keys and  stored in vocab_comments table
# Frequency of each word is calculated from stored data and output in a JSON
# Count the number of comments and store in a text file

__author__ = 'simranjitsingh'
import urllib
import time
import datetime
import json
import mysql.connector
import sys
import re
import operator
from nltk.corpus import stopwords
import nltk.tag, nltk.util, nltk.stem
from CleanTokenize import CleanAndTokenize
from ConfigParser import SafeConfigParser

# Get the config file for database
parserDb = SafeConfigParser()
# Edit the config file to fill in your credentials
parserDb.read('apidata/database.ini')

# Fetch the credentials from config file
user = parserDb.get('credentials', 'user')
password = parserDb.get('credentials', 'password')
host = parserDb.get('credentials', 'host')
database = parserDb.get('credentials', 'database')

cnx = mysql.connector.connect(user=user, password=password, host=host, database=database)
cursor = cnx.cursor()

# Get the config file for NYT Api Key/keys
parserkeys = SafeConfigParser()
# Edit the config file to fill in your api keys and values
parserkeys.read('apidata/keys_config.ini')

# Fetch the key values from config file (depends upon how many api keys you have)
COMMUNITY_API_KEY = parserkeys.get('API-KEYS', 'KEY1')
COMMUNITY_API_KEY2 = parserkeys.get('API-KEYS', 'KEY2')
COMMUNITY_API_KEY3 = parserkeys.get('API-KEYS', 'KEY3')


COMMUNITY_API_KEY_LIST = [COMMUNITY_API_KEY,COMMUNITY_API_KEY2,COMMUNITY_API_KEY3]
key_limit = 4999

doc_frequency = {}
stopword_list = stopwords.words('english')
porter = nltk.PorterStemmer()

global g_offset
global g_day
g_day = None
g_offset = None

def error_name(d,offset):
    exc_type, exc_obj, exc_tb = sys.exc_info()
    msg = str(exc_type)
    error = re.split(r'[.]',msg)
    error = re.findall(r'\w+',error[1])
    error_msg = str(error[0]) + "occured in line " + str(exc_tb.tb_lineno) + " " \
                ",Last API call date: " + str(d) + " , offset: " + str(offset)
    return error_msg

def escape_string(string):
    res = string
    res = res.replace('\\','\\\\')
    res = res.replace('\n','\\n')
    res = res.replace('\r','\\r')
    res = res.replace('\047','\134\047') # single quotes
    res = res.replace('\042','\134\042') # double quotes
    res = res.replace('\032','\134\032') # for Win32
    return res

class NYTCommunityAPI (object):
    URL = "http://api.nytimes.com/svc/community/v2/comments/by-date/"
    def __init__(self,key):
        self.nQueries = 0
        self.api_key = key
        self.QUERY_LIMIT = 30
        self.LAST_CALL = 0
        self.nCalls = 0;

    def apiCall(self, date, offset=0):
        interval = self.LAST_CALL - time.time()
        if interval < 1:
            self.nQueries += 1
            if self.nQueries >= self.QUERY_LIMIT:
                time.sleep (1)
                self.nQueries = 0

        params = {}
        params["api-key"] = self.api_key
        params["offset"] = str(offset)
        params["sort"] = "oldest"

        url = self.URL + date + ".json?" + urllib.urlencode (params)
        print url
        response = json.load(urllib.urlopen(url))
        self._LAST_CALL = time.time()
        self.nCalls += 1
        return response

# This code scrap the data from NYT API via the API keys and  stored in vocab_comments table
def CollectComments():
    try:
        pagesize = 25
        key_index = 0
        API_KEY = COMMUNITY_API_KEY_LIST[key_index]
        nytapi = NYTCommunityAPI(API_KEY)
        d_start, d_end = date_validate()
        d = d_start
        global g_offset
        global g_day
        count = 0
        while d < d_end:
            g_day = d
            offset = 0
            date_string = d.strftime("%Y%m%d")
            #Get the total # of comments for today
            r = nytapi.apiCall(date_string, offset)
            totalCommentsFound = r["results"]["totalCommentsFound"]
            print "Total comments found: " + str(totalCommentsFound)
            count += 1
            # Loop through pages to get all comments
            while offset < totalCommentsFound:
                g_offset = offset
                if count >= key_limit:
                    key_index += 1
                    count = 0
                    if key_index >= len(COMMUNITY_API_KEY_LIST):
                        d_end = d
                        print "last call on date: " + str(d)
                        print "last offset value: " + str(offset-25)
                        break;
                    API_KEY = COMMUNITY_API_KEY_LIST[key_index]
                    nytapi = NYTCommunityAPI(API_KEY)

                r = nytapi.apiCall(date_string, offset)
                # DB insertion call here.
                if "comments" in r["results"]:
                    for comment in r["results"]["comments"]:
                        commentBody = escape_string(str(comment["commentBody"].encode("utf8")))
                        approveDate = int(comment["approveDate"])
                        recommendationCount = int(comment["recommendationCount"])
                        display_name = escape_string(str(comment["display_name"].encode("utf8")))
                        location = ""
                        if "location" in r:
                            location = escape_string(str(comment["location"].encode("utf8")))
                        commentSequence = int(comment["commentSequence"])
                        status = escape_string(str(comment["status"].encode("utf8")))
                        articleURL = escape_string(str(comment["articleURL"].encode('utf8')))
                        editorsSelection = int(comment["editorsSelection"])
                        insert_query = "INSERT INTO vocab_comments (status, commentSequence, commentBody," \
                                       " approveDate, recommendationCount, editorsSelection, display_name," \
                                       " location, articleURL)" \
                                       " VALUES('%s', %d, '%s', FROM_UNIXTIME(%d), %d, %d, '%s', '%s', '%s')" % \
                                       (status.decode("utf8"), commentSequence, commentBody.decode("utf8"), approveDate,
                                        recommendationCount, editorsSelection, display_name.decode("utf8"),
                                        location.decode("utf8"), articleURL.decode("utf8"))

                        cursor.execute(insert_query)

                cnx.commit()
                offset = offset + pagesize
                count += 1
                print "#Calls: " + str(nytapi.nCalls)
                print "counter value: " + str(count)
            # Go to next day
            d += datetime.timedelta(days=1)
    except:
        print error_name(g_day,g_offset)
        sys.exit(1)

# Frequency of each word is calculated from stored data and output in a JSON
def ComputeVocabulary():
    try:
        cursor.execute("select commentBody from vocab_comments")
        n = 0
        for row in cursor:
            n = n + 1
            if n % 100 == 0 :
                print n
            ct = CleanAndTokenize(row[0])
            ct = [w for w in ct if w not in stopword_list]
            stemmed_tokens = [porter.stem(t) for t in ct]
            for t in stemmed_tokens:
                 if t not in doc_frequency:
                     doc_frequency[t] = 1
                 else:
                     doc_frequency[t] = doc_frequency[t]+1
        sorted_list = sorted(doc_frequency.items(), key=operator.itemgetter(1), reverse=True)
        # find cutoff
        unigram_cutoff = 0
        json_data = {}
        out_file = open("apidata/vocab_freq.json","w")
        for (i, (word, word_freq)) in enumerate(sorted_list):
            if word_freq < 10:
                unigram_cutoff = i - 1
                break;
            json_data[word] = word_freq
        json.dump(json_data,out_file)
        print "unigram cutoff: " + str(unigram_cutoff)
    except:
        print error_name(g_day,g_offset)
        sys.exit(1)

def date_validate():
    start_date = raw_input("Enter start date(YYYY-MM-DD): ")
    end_date = raw_input("Enter end date(YYYY-MM-DD): ")
    try:
        datetime.datetime.strptime(start_date, '%Y-%m-%d')
        datetime.datetime.strptime(end_date, '%Y-%m-%d')
    except:
         print "Incorrect date format, should be YYYY-MM-DD"
         sys.exit(1)
    start_dateOBJ = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dateOBJ = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

    if end_dateOBJ <= start_dateOBJ:
        print "End date must be greater than start date"
        sys.exit(1)
    return (start_dateOBJ,end_dateOBJ)

# Count the number of comments and store in a text file
def getDocumentCount():
    try:
        text_file = open("apidata/count.txt", "w")
        cursor.execute("select count(*) from vocab_comments")
        for i in cursor:
            text_file.write(str(i[0]))
        text_file.close()
    except:
        print error_name(g_day,g_offset)
        sys.exit(1)


CollectComments()
ComputeVocabulary()
getDocumentCount()