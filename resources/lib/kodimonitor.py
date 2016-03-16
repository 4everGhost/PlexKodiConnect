# -*- coding: utf-8 -*-

###############################################################################

import json

import xbmc
import xbmcgui

import downloadutils
import embydb_functions as embydb
import playbackutils as pbutils
import utils
from PlexFunctions import scrobble

###############################################################################


@utils.logging
class KodiMonitor(xbmc.Monitor):

    def __init__(self):

        self.doUtils = downloadutils.DownloadUtils()

        self.logMsg("Kodi monitor started.", 1)

    def onScanStarted(self, library):
        self.logMsg("Kodi library scan %s running." % library, 2)
        if library == "video":
            utils.window('emby_kodiScan', value="true")

    def onScanFinished(self, library):
        self.logMsg("Kodi library scan %s finished." % library, 2)
        if library == "video":
            utils.window('emby_kodiScan', clear=True)

    def onSettingsChanged(self):
        # Monitor emby settings
        # Review reset setting at a later time, need to be adjusted to account for initial setup
        # changes.
        '''currentPath = utils.settings('useDirectPaths')
        if utils.window('emby_pluginpath') != currentPath:
            # Plugin path value changed. Offer to reset
            self.logMsg("Changed to playback mode detected", 1)
            utils.window('emby_pluginpath', value=currentPath)
            resp = xbmcgui.Dialog().yesno(
                                heading="Playback mode change detected",
                                line1=(
                                    "Detected the playback mode has changed. The database "
                                    "needs to be recreated for the change to be applied. "
                                    "Proceed?"))
            if resp:
                utils.reset()'''

        currentLog = utils.settings('logLevel')
        if utils.window('emby_logLevel') != currentLog:
            # The log level changed, set new prop
            self.logMsg("New log level: %s" % currentLog, 1)
            utils.window('emby_logLevel', value=currentLog)

    def onNotification(self, sender, method, data):

        doUtils = self.doUtils
        if method not in ("Playlist.OnAdd"):
            self.logMsg("Method: %s Data: %s" % (method, data), 1)
            
        if data:
            data = json.loads(data,'utf-8')

        if method == "Player.OnPlay":
            # Set up report progress for emby playback
            item = data.get('item')
            try:
                kodiid = item['id']
                type = item['type']
            except (KeyError, TypeError):
                self.logMsg("Item is invalid for playstate update.", 1)
            else:
                if ((utils.settings('useDirectPaths') == "1" and not type == "song") or
                        (type == "song" and utils.settings('enableMusic') == "true")):
                    # Set up properties for player
                    with embydb.GetEmbyDB() as emby_db:
                        emby_dbitem = emby_db.getItem_byKodiId(kodiid, type)
                    try:
                        itemid = emby_dbitem[0]
                    except TypeError:
                        self.logMsg("No kodiid returned.", 1)
                    else:
                        # Tell everyone else what's going on
                        utils.window('Plex_currently_playing_itemid',
                                     value=itemid)
                        url = "{server}/library/metadata/%s" % itemid
                        result = doUtils.downloadUrl(url)
                        try:
                            result.attrib
                        except AttributeError:
                            self.logMsg('Could not retrieve PMS xml for %s'
                                        % itemid, -1)
                            return
                        playurl = None
                        count = 0
                        while not playurl and count < 2:
                            try:
                                playurl = xbmc.Player().getPlayingFile()
                            except RuntimeError:
                                count += 1
                                xbmc.sleep(200)
                            else:
                                listItem = xbmcgui.ListItem()
                                playback = pbutils.PlaybackUtils(result)

                                if type == "song" and utils.settings('streamMusic') == "true":
                                    utils.window('emby_%s.playmethod' % playurl,
                                        value="DirectStream")
                                else:
                                    utils.window('emby_%s.playmethod' % playurl,
                                        value="DirectPlay")
                                # Set properties for player.py
                                playback.setProperties(playurl, listItem)

        elif method == "Player.OnStop":
            # Get rid of some values
            utils.window('Plex_currently_playing_itemid', clear=True)

        elif method == "VideoLibrary.OnUpdate":
            # Manually marking as watched/unwatched
            playcount = data.get('playcount')
            item = data.get('item')
            try:
                kodiid = item['id']
                type = item['type']
            except (KeyError, TypeError):
                self.logMsg("Item is invalid for playstate update.", 1)
            else:
                # Send notification to the server.
                with embydb.GetEmbyDB() as emby_db:
                    emby_dbitem = emby_db.getItem_byKodiId(kodiid, type)
                try:
                    itemid = emby_dbitem[0]
                except TypeError:
                    self.logMsg("Could not find itemid in emby database.", 1)
                else:
                    # Stop from manually marking as watched unwatched, with actual playback.
                    if utils.window('emby_skipWatched%s' % itemid) == "true":
                        # property is set in player.py
                        utils.window('emby_skipWatched%s' % itemid, clear=True)
                    else:
                        # notify the server
                        if playcount != 0:
                            scrobble(itemid, 'watched')
                        else:
                            scrobble(itemid, 'unwatched')

        elif method == "VideoLibrary.OnRemove":
            # Removed function, because with plugin paths + clean library, it will wipe
            # entire library if user has permissions. Instead, use the emby context menu available
            # in Isengard and higher version
            pass
            '''try:
                kodiid = data['id']
                type = data['type']
            except (KeyError, TypeError):
                self.logMsg("Item is invalid for emby deletion.", 1)
            else:
                # Send the delete action to the server.
                embyconn = utils.kodiSQL('emby')
                embycursor = embyconn.cursor()
                emby_db = embydb.Embydb_Functions(embycursor)
                emby_dbitem = emby_db.getItem_byKodiId(kodiid, type)
                try:
                    itemid = emby_dbitem[0]
                except TypeError:
                    self.logMsg("Could not find itemid in emby database.", 1)
                else:
                    if utils.settings('skipContextMenu') != "true":
                        resp = xbmcgui.Dialog().yesno(
                                                heading="Confirm delete",
                                                line1="Delete file on Emby Server?")
                        if not resp:
                            self.logMsg("User skipped deletion.", 1)
                            embycursor.close()
                            return

                    url = "{server}/emby/Items/%s?format=json" % itemid
                    self.logMsg("Deleting request: %s" % itemid)
                    doUtils.downloadUrl(url, type="DELETE")
                finally:
                    embycursor.close()'''


        elif method == "System.OnWake":
            # Allow network to wake up
            xbmc.sleep(10000)
            utils.window('emby_onWake', value="true")

        elif method == "Playlist.OnClear":
            pass