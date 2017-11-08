# -*- coding: utf-8 -*-

"""
***************************************************************************
    layertracking.py
    ---------------------
    Date                 : March 2016
    Copyright            : (C) 2016 Boundless, http://boundlessgeo.com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
from builtins import range
from builtins import object
import sqlite3

__author__ = 'Victor Olaya'
__date__ = 'March 2016'
__copyright__ = '(C) 2016 Boundless, http://boundlessgeo.com'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'


import os
import json
from json.decoder import JSONDecoder
from json.encoder import JSONEncoder

from geogig import config
from geogig.tools.utils import userFolder
from geogig.tools.layers import  layerFromSource, WrongLayerSourceException
from geogig.tools.layers import formatSource

from qgiscommons2.layers import vectorLayers, loadLayerNoCrsDialog

from qgis.core import QgsVectorLayer

tracked = []

class Encoder(JSONEncoder):
    def default(self, o):
        return o.__dict__

def decoder(jsonobj):
    if 'source' in jsonobj:
        return TrackedLayer(jsonobj['source'],
                            jsonobj['repoUrl'])
    else:
        return jsonobj

class TrackedLayer(object):
    def __init__(self, source, repoUrl):
        self.repoUrl = repoUrl
        self.source = source
        self.geopkg, self.layername = source.split("|")
        self.layername = self.layername.split("=")[-1]


def addTrackedLayer(source, repoFolder):
    global tracked
    source = formatSource(source)
    layer = TrackedLayer(source, repoFolder)
    if layer not in tracked:
        for lay in tracked:
            if lay.source == source:
                tracked.remove(lay)
        tracked.append(layer)
        saveTracked()


def removeTrackedLayer(layer):
    global tracked
    source = formatSource(layer)
    for i, obj in enumerate(tracked):
        if obj.source == source:
            del tracked[i]
            saveTracked()
            return

def removeTrackedForRepo(repo):
    global tracked

    for i in range(len(tracked) - 1, -1, -1):
        layer = tracked[i]
        if layer.repoUrl == repo.url:
            del tracked[i]
    saveTracked()

def removeNonexistentTrackedLayers():
    global tracked
    for i in range(len(tracked) - 1, -1, -1):
        layer = tracked[i]
        if not os.path.exists(layer.geopkg):
            del tracked[i]
    saveTracked()

def saveTracked():
    filename = os.path.join(userFolder(), "trackedlayers")
    with open(filename, "w") as f:
        f.write(json.dumps(tracked, cls = Encoder))

def readTrackedLayers():
    try:
        global tracked
        filename = os.path.join(userFolder(), "trackedlayers")
        if os.path.exists(filename):
            with open(filename) as f:
                lines = f.readlines()
            jsonstring = "\n".join(lines)
            if jsonstring:
                tracked = JSONDecoder(object_hook = decoder).decode(jsonstring)
    except KeyError:
        pass

def isRepoLayer(layer):
    if isinstance(layer, QgsVectorLayer):
        return getTrackingInfo(layer) is not None
    else:
        return False

def getTrackingInfo(layer):
    source = formatSource(layer)
    for obj in tracked:
        if obj.source == source:
            return obj
    return None


def getTrackingInfoForGeogigLayer(repoUrl, layername, commitId = None):
    ret = []
    for t in tracked:
        if (t.repoUrl == repoUrl and t.layername == layername):
            if os.path.exists(t.geopkg):
                if commitId:
                    try:
                        con = sqlite3.connect(t.geopkg)
                        cursor = con.cursor()
                        cursor.execute("SELECT commit_id FROM geogig_audited_tables WHERE table_name='%s';" % layername)
                        currentCommitId = cursor.fetchone()[0]
                        cursor.close()
                        con.close()
                        if commitId == currentCommitId:
                            return t
                    except:
                        pass
                else:
                    ret.append(t)
    return ret

def getProjectLayerForGeoGigLayer(repoUrl, layername):
    tracked = getTrackingInfoForGeogigLayer(repoUrl, layername)
    ret = []
    layers = vectorLayers()
    for t in tracked:
        for layer in layers:
            if formatSource(layer) == t.source:
                ret.append(t)
    return ret

def getTrackedPathsForRepo(repo):
    repoLayers = repo.trees()
    trackedPaths = [layer.source for layer in tracked
                if repo.url == layer.repoUrl and layer.layername in repoLayers]
    return trackedPaths
