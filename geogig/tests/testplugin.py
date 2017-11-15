# -*- coding: utf-8 -*-

"""
***************************************************************************
    testerplugin.py
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

__author__ = 'Victor Olaya'
__date__ = 'March 2016'
__copyright__ = '(C) 2016 Boundless, http://boundlessgeo.com'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import sys
import sqlite3
from sqlite3 import OperationalError
import unittest
import shutil
from distutils.dir_util import copy_tree

from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsFeature, QgsGeometry, QgsPoint, edit
from qgis.utils import iface

from geogig import tests
from geogig.layeractions import updateInfoActions
from geogig.geogigwebapi import repository
from geogig import layeractions

from geogig.gui.dialogs.navigatordialog import navigatorInstance

from geogig.tests import conf, _createSimpleTestRepo, _createEmptyTestRepo, _createMultilayerTestRepo
from geogig.tests.testwebapilib import webapiSuite
from geogig.tests.testgpkg import GeoPackageEditTests

from geogig.tools import layertracking
from geogig.tools.gpkgsync import applyLayerChanges, getCommitId, checkoutLayer

from qgiscommons2.files import tempFolderInTempFolder, tempFilename
from qgiscommons2.layers import loadLayerNoCrsDialog, layerFromName

def openTestProject(name):
    orgPath = os.path.join(os.path.dirname(__file__), "data", "projects", name)
    destPath = tempFolderInTempFolder()
    copy_tree(orgPath, destPath)
    projectFile = os.path.join(destPath, name + ".qgs")
    if projectFile != QgsProject.instance().fileName():
        iface.addProject(projectFile)

_repos = []
_repoEndpoints = {}
_availableRepoEndpoints = {}
_tracked = []

def backupConfiguration():
    global _repos
    global _repoEndpoints
    global _availableRepoEndpoints
    _repos = repository.repos
    _repoEndpoints = repository.repoEndpoints
    _availableRepoEndpoints = repository.availableRepoEndpoints
    _tracked = layertracking.tracked

def restoreConfiguration():
    global _repos
    global _tracked
    global _repoEndpoints
    global _availableRepoEndpoints
    repository.repoEndpoints = _repoEndpoints
    repository.availableRepoEndpoints = _availableRepoEndpoints
    repository.repos = _repos
    layertracking._tracked = _tracked

def _openNavigator(empty = False, group = "test", repos = None):
    if empty:
        repository.repos = []
        repository.repoEndpoints = {}
        repository.availableRepoEndpoints = {}
    else:
        if repos is None:
            repos = [tests._lastRepo]
        repository.repos = repos
        repository.availableRepoEndpoints = {group:conf['REPOS_SERVER_URL']}
        repository.repoEndpoints = {group:conf['REPOS_SERVER_URL']}
    action = navigatorInstance.toggleViewAction()
    if not action.isChecked():
        iface.addDockWidget(Qt.RightDockWidgetArea, navigatorInstance)
    action.trigger()
    action.trigger()
    navigatorInstance.updateNavigator()


def _exportAndEditLayer():
    layer = checkoutLayer(tests._lastRepo, "points", None)
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1000)
        layer.deleteFeatures([features[1].id()])
        feat = QgsFeature(layer.pendingFields())
        feat.setAttributes(["5", 5])
        feat.setGeometry(QgsGeometry.fromPoint(QgsPoint(123, 456)))
        layer.addFeatures([feat])
    return layer

def _addNewCommit():
    layer = _exportAndEditLayer()
    tests._lastRepo.importgeopkg(layer, "master", "message", "me", "me@mysite.com", True)

def _exportAndChangeToFirstVersion():
    layer = checkoutLayer(tests._lastRepo, "points", None)
    log = tests._lastRepo.log()
    assert len(log) == 3
    commitid = log[-1].commitid
    applyLayerChanges(tests._lastRepo, layer, tests._lastRepo.HEAD, commitid)
    updateInfoActions(layer)
    layer.reload()
    layer.triggerRepaint()

def _exportChangetoFirstVersionAndEditLayer():
    log = tests._lastRepo.log()
    assert len(log) == 3
    commitid = log[-1].commitid
    layer = checkoutLayer(tests._lastRepo, "points", None, commitid)
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1000)
        feat = QgsFeature(layer.pendingFields())
        feat.setAttributes(["5", 5])
        feat.setGeometry(QgsGeometry.fromPoint(QgsPoint(123, 456)))
        layer.addFeatures([feat])

def _exportAndAddFeatureToLayer():
    layer = checkoutLayer(tests._lastRepo, "points", None)
    log = tests._lastRepo.log()
    assert len(log) == 3
    commitid = log[-1].commitid
    applyLayerChanges(tests._lastRepo, layer, tests._lastRepo.HEAD, commitid)
    updateInfoActions(layer)
    with edit(layer):
        feat = QgsFeature(layer.pendingFields())
        feat.setAttributes(["5", 5])
        feat.setGeometry(QgsGeometry.fromPoint(QgsPoint(123, 456)))
        layer.addFeatures([feat])
    layer.reload()
    layer.triggerRepaint()

def _exportAndCreateConflictWithNulls():
    layer = checkoutLayer(tests._lastRepo, "points", None)
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.changeGeometry(features[0].id(), QgsGeometry.fromPoint(QgsPoint(123, 456)))
        layer.changeAttributeValue(features[0].id(), idx, None)
    filename = tempFilename("gpkg")
    tests._lastRepo.checkoutlayer(filename, "points")
    layer2 = loadLayerNoCrsDialog(filename, "points2", "ogr")
    features2 = list(layer2.getFeatures())
    with edit(layer2):
        layer2.changeGeometry(features[0].id(), QgsGeometry.fromPoint(QgsPoint(124, 457)))
        layer2.changeAttributeValue(features2[0].id(), idx, None)
    _, _, conflicts, _ = tests._lastRepo.importgeopkg(layer2, "master", "message", "me", "me@mysite.com", True)

def _exportAndCreateConflict():
    layer = checkoutLayer(tests._lastRepo, "points", None)
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1000)
    filename = tempFilename("gpkg")
    tests._lastRepo.checkoutlayer(filename, "points")
    layer2 = loadLayerNoCrsDialog(filename, "points2", "ogr")
    features2 = list(layer2.getFeatures())
    with edit(layer2):
        layer2.changeAttributeValue(features2[0].id(), idx, 1001)
    _, _, conflicts, _ = tests._lastRepo.importgeopkg(layer2, "master", "message", "me", "me@mysite.com", True)

def _exportAndCreateConflictWithRemoveAndModify():
    layer = checkoutLayer(tests._lastRepo, "points", None)
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.deleteFeatures([features[0].id()])
    filename = tempFilename("gpkg")
    tests._lastRepo.checkoutlayer(filename, "points")
    layer2 = loadLayerNoCrsDialog(filename, "points2", "ogr")
    features2 = list(layer2.getFeatures())
    with edit(layer2):
        layer2.changeAttributeValue(features[0].id(), idx, 1000)
    _, _, conflicts, _ = tests._lastRepo.importgeopkg(layer2, "master", "message", "me", "me@mysite.com", True)

def _deleteLayerFromBranch():
    tests._lastRepo.removetree("points", "me", "me@mysite.com", "mybranch")

def _createMergeScenario(layername = "points"):
    filename = tempFilename("gpkg")
    tests._lastRepo.checkoutlayer(filename, layername)
    layer = loadLayerNoCrsDialog(filename, layername, "ogr")
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1000)
    tests._lastRepo.importgeopkg(layer, "mybranch", "changed_%s_1" % layername, "me", "me@mysite.com", True)

def _doConflictImport(layername = "points"):
    filename = tempFilename("gpkg")
    tests._lastRepo.checkoutlayer(filename, layername)
    layer = loadLayerNoCrsDialog(filename, layername, "ogr")
    idx = layer.dataProvider().fieldNameIndex("n")
    features = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1001)
    tests._lastRepo.importgeopkg(layer, "master", "changed_%s_2" % layername, "me", "me@mysite.com", True)

def _createMergeConflict():
    _createMergeScenario("points")
    _doConflictImport("points")

def _createMergeConflictInSeveralLayers():
    _createMergeScenario("points")
    _createMergeScenario("lines")
    _doConflictImport("points")
    _doConflictImport("lines")

_localRepo = None
_remoteRepo = None
def _createConflictedPullScenario():
    _createPullScenario()
    filename = tempFilename("gpkg")
    _localRepo.checkoutlayer(filename, "points")
    layer = loadLayerNoCrsDialog(filename, "points", "ogr")
    features = list(layer.getFeatures())
    idx = layer.dataProvider().fieldNameIndex("n")
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1000)
    _localRepo.importgeopkg(layer, "master", "message", "me", "me@mysite.com", True)

def _createPullScenario():
    global _remoteRepo
    _remoteRepo = _createEmptyTestRepo(True)
    global _localRepo
    _localRepo = _createSimpleTestRepo(True)
    _localRepo.addremote("myremote", _remoteRepo.url)
    _remoteRepo.addremote("myremote", _localRepo.url)
    _localRepo.push("myremote", "master")
    filename = tempFilename("gpkg")
    _remoteRepo.checkoutlayer(filename, "points")
    layer = loadLayerNoCrsDialog(filename, "points", "ogr")
    idx = layer.dataProvider().fieldNameIndex("n")
    features  = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1001)
    _remoteRepo.importgeopkg(layer, "master", "message2", "me", "me@mysite.com", True)

def _createNothingToPushScenario():
    global _remoteRepo
    _remoteRepo = _createEmptyTestRepo(True)
    global _localRepo
    _localRepo = _createSimpleTestRepo(True)
    _localRepo.addremote("myremote", _remoteRepo.url)
    _remoteRepo.addremote("myremote", _localRepo.url)
    _localRepo.push("myremote", "master")

def _createPushScenario():
    _createNothingToPushScenario()
    filename = tempFilename("gpkg")
    _localRepo.checkoutlayer(filename, "points")
    layer = loadLayerNoCrsDialog(filename, "points", "ogr")
    idx = layer.dataProvider().fieldNameIndex("n")
    features  = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[0].id(), idx, 1001)
    _localRepo.importgeopkg(layer, "master", "message", "me", "me@mysite.com", True)

def _createCannotPushScenario():
    _createPushScenario()
    filename = tempFilename("gpkg")
    _remoteRepo.checkoutlayer(filename, "points")
    layer = loadLayerNoCrsDialog(filename, "points", "ogr")
    idx = layer.dataProvider().fieldNameIndex("n")
    features  = list(layer.getFeatures())
    with edit(layer):
        layer.changeAttributeValue(features[1].id(), idx, 1001)
    _remoteRepo.importgeopkg(layer, "master", "message", "me", "me@mysite.com", True)






def _exportLayer():
    checkoutLayer(tests._lastRepo, "points", None)

def _selectLayer():
    layer = layerFromName("points")
    iface.setActiveLayer(layer)

def _checkLayerInProject():
    layer = layerFromName("points")
    assert layer is not None

def _checkLayerInRepo():
    assert "points" in tests._lastRepo.trees()

def _checkLayerHasUntrackedContextMenus():
    layer = layerFromName("points")
    actions = layeractions._actions[layer.id()]
    assert 1 == len(actions)
    assert "add" in actions[0].text().lower()

def _checkLayerHasTrackedContextMenus():
    layer = layerFromName("points")
    actions = layeractions._actions[layer.id()]
    assert 1 < len(actions)
    assert "commit id" in actions[-1].text().lower()

def _checkContextMenuInfo(text):
    layer = layerFromName("points")
    actions = layeractions._infoActions[layer.id()]
    assert 2 == len(actions)
    assert text in actions[0].text().lower()

def _removeRepos():
    repository.repos = []

#TESTS

def settings():
    return {"REPOS_SERVER_URL": "http://localhost:8182/"}

def functionalTests():
    try:
        from qgistester.test import Test
        class GeoGigTest(Test):
            def __init__(self, name, category = "General"):
                Test.__init__(self, name, category)
                self.addStep("Preparing test", backupConfiguration)
                self.setCleanup(restoreConfiguration)

    except:
        return []

    tests = []

    test = GeoGigTest("Connect to endpoint")
    test.addStep("Open navigator", lambda:  _openNavigator(True))
    test.addStep("Add a new geogig server at the repositories server url")
    test.addStep("Verify the endpoint item has been correctly added (might contain child repos or not)")
    tests.append(test)

    test = GeoGigTest("Connect to wrong endpoint")
    test.addStep("Open navigator", lambda:  _openNavigator(True))
    test.addStep("Add a new geogig server at 'http://wrong.url'")
    test.addStep("Verify a warning indicating that the url is wrong is shown. Verify endpoint item is added to tree and grayed out.")
    tests.append(test)

    test = GeoGigTest("Add layer without repo")
    test.addStep("Open test data", lambda: openTestProject("points"))
    test.addStep("Open navigator", lambda:  _openNavigator(True))
    test.addStep("Right click on the layer and try to add it to a repository.\n"
                 "Verify that it shows a warning because there are no repositories defined.")
    tests.append(test)

    test = GeoGigTest("Add layer to repository")
    test.addStep("Open test data", lambda: openTestProject("points"))
    test.addStep("Create repository", lambda: _createEmptyTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Add layer 'points' to the 'empty' repository using layer's context menu")
    test.addStep("Check layer has been added to repo", _checkLayerInRepo)
    tests.append(test)

    test = GeoGigTest("Edit and delete endpoint")
    test.addStep("Create repository", lambda: _createEmptyTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Change endpoint name by pressing 'Edit' button. Verify that name changed and no error is thrown")
    test.addStep("Remove endpoint by pressing 'Delete' button. Verify that endpoint removed and buttons desctivated")
    tests.append(test)

    test = GeoGigTest("Add geopackage with multiple layers to repository")
    test.addStep("Open test data", lambda: openTestProject("multilayer"))
    test.addStep("Create repository", lambda: _createEmptyTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Add layer 'points' to the 'empty' repository using layer's context menu")
    test.addStep("Check that warning message shown and no error is thrown")
    tests.append(test)

    test = GeoGigTest("Check repository log")
    test.addStep("Create repository", lambda: _createSimpleTestRepo())
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Check log is correctly displayed in the history tab of the GeoGig navigator")
    tests.append(test)

    test = GeoGigTest("Open repository layers in QGIS", "Export layers tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("New project", iface.newProject)
    test.addStep("Add layer from the 'simple' repository into QGIS. To do it, right-click in the layer item of the repository tree and use the corresponding context menu entry.")
    test.addStep("Check layer has been added to project", _checkLayerInProject)
    tests.append(test)

    test = GeoGigTest("Open repository layers in QGIS from tree", "Export layers tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("New project", iface.newProject)
    test.addStep("Add layer from the 'simple' repository into QGIS. To do it, right-click in the layer item of the repository tree and use the corresponding context menu entry.")
    test.addStep("Check layer has been added to project", _checkLayerInProject)
    tests.append(test)

    test = GeoGigTest("Open already exported layers in QGIS from tree", "Export layers tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportAndChangeToFirstVersion)
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Add layer from the 'simple' repository into QGIS. To do it, right-click in the layer item of the repository tree and use the corresponding context menu entry. "
                 "Verify that is asks you for confirmation. Select 'Use branch version'", isVerifyStep = True)
    test.addStep("Check context menu info", lambda: _checkContextMenuInfo("third"))
    tests.append(test)

    test = GeoGigTest("Open already exported layers in QGIS when there are local changes", "Export layers tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportAndEditLayer)
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Add layer from the 'simple' repository into QGIS. To do it, right-click in the layer item of the repository tree and use the corresponding context menu entry."
                 "Verify it show a message in the message bar saying that the layer was already loaded", isVerifyStep = True)
    tests.append(test)

    test = GeoGigTest("Open already exported layers in QGIS to an older version, with local changes", "Export layers tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportChangetoFirstVersionAndEditLayer)
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Add layer from the 'simple' repository into QGIS. To do it, right-click in the layer item of the repository tree and use the corresponding context menu entry.  "
                 "Verify that is asks you for confirmation. Select 'Use branch version'. Check it is not permitted due to local changes in the layer",
                 isVerifyStep = True)
    tests.append(test)

    test = GeoGigTest("Open layers in QGIS from history tree", "Export layers tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Add layer from the 'simple' repository into QGIS. To do it, right-click in the last commit of the 'master' branch in the history tree and use the corresponding context menu entry."
                 "Check a layer is correctly added",
                 isVerifyStep = True)
    test.addStep("Update layer from the 'simple' repository into QGIS. To do it, right-click in the last commit of the 'mybranch' branch in the history tree and use the corresponding context menu entry."
                 "Check that a warning message is shown. Select to overwrite the layer and verify it is updated",
                 isVerifyStep = True)
    tests.append(test)

    test = GeoGigTest("Change layer version", "Export layers tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportAndChangeToFirstVersion)
    test.addStep("Change version to 'third' using the 'Change version' menu entry in the layer context menu")
    test.addStep("Check layer has been added to project", _checkLayerInProject)
    test.addStep("Check context menu info", lambda: _checkContextMenuInfo("third"))
    tests.append(test)

    test = GeoGigTest("Change layer version when there are local changes", "Export layers tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportAndEditLayer)
    test.addStep("Try to change version using the 'Change version' menu entry in the layer context menu."
                 "Check it is not permitted due to local changes in the layer", isVerifyStep = True)
    tests.append(test)

    test = Test("Sync with only local changes", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Export and edit repo layer", _exportAndEditLayer)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch'")
    test.addStep("Check in repo history that a new version has been created")
    tests.append(test)

    test = Test("Sync to non-master branch", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Export and edit repo layer", _exportAndEditLayer)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Select 'mybranch' in the branch box and sync'")
    test.addStep("Check in repo history that the 'mybranch' branch has been updated with the changes")
    tests.append(test)

    test = Test("Sync with only upstream changes", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Export repo layer", _exportAndChangeToFirstVersion)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch'")
    test.addStep("Check context menu info", lambda: _checkContextMenuInfo("third"))
    test.addStep("Check that layer has been modified")
    tests.append(test)

    test = Test("Sync with no changes at all", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportLayer)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch'")
    test.addStep("Check context menu info", lambda: _checkContextMenuInfo("third"))
    test.addStep("Check that no changes are made in the layer or the history")
    tests.append(test)

    test = Test("Merge without conflicts", "Merge tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Create merge conflict", _createMergeScenario)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Merge 'mybranch' branch into 'master' branch")
    test.addStep("Check that the merge was correctly completed")
    tests.append(test)

    test = Test("Merge with conflicts", "Merge tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Create merge conflict", _createMergeConflict)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Merge 'mybranch' branch into 'master' branch. Solve conflict")
    test.addStep("Check that the merge was correctly completed")
    tests.append(test)

    test = Test("Merge with conflicts in several layers", "Merge tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createMultilayerTestRepo(True))
    test.addStep("Create merge conflict", _createMergeConflictInSeveralLayers)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Merge 'mybranch' branch into 'master' branch. Solve conflict")
    test.addStep("Check that the merge was correctly completed")
    tests.append(test)

    test = Test("Sync with conflicts", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export and edit repo layer", _exportAndCreateConflict)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch. Solve conflict'")
    test.addStep("Check that new version has been created in the repo history")
    tests.append(test)

    test = Test("Sync with conflict, with remove and modify", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export and edit repo layer", _exportAndCreateConflictWithRemoveAndModify)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch. Solve conflict'")
    test.addStep("Check that new version has been created in the repo history")
    tests.append(test)

    test = Test("Sync with conflicts and null values", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export and edit repo layer", _exportAndCreateConflictWithNulls)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch. Solve conflict with a new feature'")
    test.addStep("Check that new version has been created in the repo history")
    tests.append(test)

    test = Test("Sync with conflicts, without resolving them", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export and edit repo layer", _exportAndCreateConflict)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch'. Sync with master branch. Exit conflict dialog without solving'")
    test.addStep("Check that no new version has been created in the repo history, and the layer hasn't been modified")
    tests.append(test)

    test = Test("Sync with both local and upstream changes, without conflict", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Export and edit repo layer", _exportAndAddFeatureToLayer)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch. Sync with master branch'")
    test.addStep("Check that layer has been modified and a new version has been created in the repo history")
    tests.append(test)

    test = Test("Sync with layer only in one branch", "Synchronization tests")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Export repo layer", _exportLayer)
    test.addStep("Delete layer from branch", _deleteLayerFromBranch)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Sync with repository branch. Verify that only 'master'branch is available")
    tests.append(test)

    test = Test("Pull without conflicts")
    test.addStep("New project", iface.newProject)
    test.addStep("Prepare test", _createPullScenario)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Select the repository in the repository explorer. Pull from 'myremote' into'master' branch. Verify the pull operation id performed correctly.")
    tests.append(test)

    test = Test("Push")
    test.addStep("New project", iface.newProject)
    test.addStep("Prepare test", _createPushScenario)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Select the repository in the repository explorer. Push to 'myremote' repo . Verify the push operation id performed correctly.")
    tests.append(test)

    test = Test("Pull with conflicts")
    test.addStep("New project", iface.newProject)
    test.addStep("Prepare test", _createConflictedPullScenario)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Select the repository in the repository explorer. Pull from 'myremote' into'master' branch. It will warn you of existing conflict. Solve conflicts and verify it finishes the pull operation correctly.")
    tests.append(test)

    test = Test("Nothing to push")
    test.addStep("New project", iface.newProject)
    test.addStep("Prepare test", _createNothingToPushScenario)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Select the repository in the repository explorer. Push to 'myremote' repo . Verify the push operation is not performed and the corresponding message is displayed.")
    tests.append(test)

    test = Test("TEST SCENARIO: Two cloned repos")
    test.addStep("New project", iface.newProject)
    test.addStep("Prepare test", _createNothingToPushScenario)
    test.addStep("Open navigator", lambda: _openNavigator(repos = [_remoteRepo, _localRepo]))
    test.addStep("TEST ON THE LOCAL AND REMOTE REPOS")
    tests.append(test)

    test = Test("Cannot push")
    test.addStep("New project", iface.newProject)
    test.addStep("Prepare test", _createCannotPushScenario)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Select the repository in the repository explorer. Push to 'myremote' repo . Verify the push operation is performed correctly.")
    tests.append(test)

    test = Test("Check diff viewer")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo())
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Click on latest commit and select 'View changes'. Check that diff viewer works correctly", isVerifyStep = True)
    test.addStep("Select two commits, right-click and select 'View changes'. Check that diff viewer works correctly", isVerifyStep = True)
    test.addStep("Select the two branch items in the history tree, right-click and select 'View changes'. Check that diff viewer works correctly", isVerifyStep = True)
    tests.append(test)

    test = Test("Check local diff viewer")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export and edit repo layer", _exportAndEditLayer)
    test.addStep("Right click on 'points' layer and select 'GeoGig/view local changes'. Check that diff viewer works correctly")
    tests.append(test)

    test = Test("Check export diff layer")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Add commit", _addNewCommit)
    test.addStep("Open navigator",  _openNavigator)
    test.addStep("Click on latest commit in master branch and select 'Export diff as layer'. Check that layer is exported correctly")
    tests.append(test)

    test = GeoGigTest("Add layer to repository from context menu")
    test.addStep("Open test data", lambda: openTestProject("points"))
    test.addStep("Create repository", lambda: _createEmptyTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Add layer using context menu")
    test.addStep("Check layer has been added to repo", _checkLayerInRepo)
    test.addStep("Check layer context menus", _checkLayerHasTrackedContextMenus)
    tests.append(test)

    test = GeoGigTest("Show version characteristics")
    test.addStep("Create repository", lambda: _createSimpleTestRepo())
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Right click on repo's last commit and select 'Show detailed description'\nVerify description is correctly shown")
    tests.append(test)

    test = GeoGigTest("Create new branch", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Create new branch at master branch's last commit and verify it is added to history tree")
    tests.append(test)

    test = GeoGigTest("Delete branch", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Verify that 'master' branch cannot be deleted from history tree", isVerifyStep = True)
    test.addStep("Delete 'mybranch' using repo history panel and verify the history tree is updated")
    tests.append(test)


    test = GeoGigTest("Create new branch from repo tree", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Create new branch at master branch using the repos tree context menu. Verify it is added to history tree")
    tests.append(test)

    test = GeoGigTest("Delete branch", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Verify that 'master' branch cannot be deleted from repos tree", isVerifyStep = True)
    test.addStep("Delete 'mybranch' using repos tree context menu panel and verify that also the history tree is updated")
    tests.append(test)

    test = GeoGigTest("Delete branch in repositories tree", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Verify that 'master' branch cannot be deleted from repositories tree", isVerifyStep = True)
    test.addStep("Delete 'mybranch' from the versions tree and verify the repositories tree is updated")
    tests.append(test)

    test = GeoGigTest("Delete layer in repositories tree, in 'master' branch")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Delete 'points' layer in 'master' branch in repositories tree, and verify the repositories tree is updated correctly")
    tests.append(test)

    test = GeoGigTest("Delete layer in tree, in non-master branch")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Delete 'points' layer in 'mybranch' branch in repositories tree, and verify the versions tree is updated correctly")
    tests.append(test)

    test = GeoGigTest("Delete layer in tree, in all branches")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportLayer)
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Delete 'points' layer in 'mybranch' branch in repositories tree, and verify the versions tree is updated correctly."
                 "Verify that the context menu of the layer still shows the tracked layer menus")
    test.addStep("Delete 'points' layer in 'master' branch in repositories tree, and verify the versions tree is updated correctly."
                 "Verify that the context menu of the layer shows the layer as untracked")
    tests.append(test)

    test = GeoGigTest("Revert commit that adds a layer")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export repo layer", _exportLayer)
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Right click on 'points' layer and select 'GeoGig/Revert commit...'. Select commit that adds layer and press OK button.")
    test.addStep("Check that warning message is shown and no error is thrown.")
    tests.append(test)

    test = GeoGigTest("Create new tag", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Create new tag at current branch's last commit and verify it is added to history tree")
    tests.append(test)

    test = GeoGigTest("Delete tag", "Branch and tag tests")
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Open navigator", _openNavigator)
    test.addStep("Delete 'mytag' tag and verify the versions tree is updated")
    tests.append(test)

    test = Test("Check map tools viewer")
    test.addStep("New project", iface.newProject)
    test.addStep("Create repository", lambda: _createSimpleTestRepo(True))
    test.addStep("Export layer", _exportLayer)
    test.addStep("Select the 'GeoGig/Info Tool' menu")
    test.addStep("Select layer", _selectLayer)
    test.addStep("Click on a feature and select 'View authorship'. Verify it shows authorship correctly", isVerifyStep = True)
    test.addStep("Click on a feature and select 'View versions'. Verify it shows feature versions correctly")
    tests.append(test)

    return tests

class PluginTests(unittest.TestCase):

    def setUp(self):
        pass

    def testChangeVersion(self):
        repo = _createSimpleTestRepo()
        log = repo.log()
        self.assertEqual(3, len(log))
        commitid = log[-1].commitid
        filename = tempFilename("gpkg")
        repo.checkoutlayer(filename, "points", ref = commitid)
        layer = loadLayerNoCrsDialog(filename, "points", "ogr")
        self.assertTrue(layer.isValid())
        features = list(layer.getFeatures())
        self.assertEqual(1, len(features))
        applyLayerChanges(repo, layer, commitid, repo.HEAD)
        layer.reload()
        self.assertTrue(layer.isValid())
        features = list(layer.getFeatures())
        self.assertEqual(2, len(features))
        self.assertEqual(getCommitId(layer), log[0].commitid)

    def testCanCleanAuditTableAfterEdit(self):
        src = os.path.join(os.path.dirname(__file__), "data", "layers", "points.gpkg")
        dest = tempFilename("gpkg")
        shutil.copy(src, dest)
        layer = loadLayerNoCrsDialog(dest, "points", "ogr")
        self.assertTrue(layer.isValid())
        features = list(layer.getFeatures())
        geom = QgsGeometry.fromPoint(QgsPoint(12,12))
        self.assertTrue(layer.startEditing())
        self.assertTrue(layer.changeGeometry(features[0].id(), geom))
        self.assertTrue(layer.commitChanges())
        con = sqlite3.connect(dest)
        cursor = con.cursor()
        cursor.execute("DELETE FROM points_audit;")
        self.assertRaises(OperationalError, con.commit)
        con.close()
        layer.reload()
        con = sqlite3.connect(dest)
        cursor = con.cursor()
        cursor.execute("DELETE FROM points_audit;")
        con.commit()


def pluginSuite():
    suite = unittest.TestSuite()
    suite.addTests(unittest.makeSuite(PluginTests, 'test'))
    return suite


def unitTests():
    _tests = []
    _tests.extend(webapiSuite())
    _tests.extend(pluginSuite())
    return _tests


def run_tests():
    unittest.TextTestRunner(verbosity=3, stream=sys.stdout).run(pluginSuite())
    unittest.TextTestRunner(verbosity=3, stream=sys.stdout).run(webapiSuite())
