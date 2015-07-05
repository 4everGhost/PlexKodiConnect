import xbmcaddon
import xbmcplugin
import xbmc
import xbmcgui
import os
import threading
import json
import inspect

import KodiMonitor
import Utils as utils

from DownloadUtils import DownloadUtils
from WebSocketClient import WebSocketThread
from PlayUtils import PlayUtils
from ClientInformation import ClientInformation
from LibrarySync import LibrarySync
from  PlaybackUtils import PlaybackUtils
from ReadEmbyDB import ReadEmbyDB
from API import API

librarySync = LibrarySync()

# service class for playback monitoring
class Player( xbmc.Player ):

    # Borg - multiple instances, shared state
    _shared_state = {}
    
    xbmcplayer = xbmc.Player()
    doUtils = DownloadUtils()
    clientInfo = ClientInformation()
    ws = WebSocketThread()

    addonName = clientInfo.getAddonName()
    addonId = clientInfo.getAddonId()
    addon = xbmcaddon.Addon(id=addonId)

    WINDOW = xbmcgui.Window(10000)

    logLevel = 0
    played_information = {}
    settings = None
    playStats = {}

    audioPref = "default"
    subsPref = "default"
    
    def __init__( self, *args ):
        
        self.__dict__ = self._shared_state
        self.logMsg("Starting playback monitor service", 1)
        
    def logMsg(self, msg, lvl=1):
        
        self.className = self.__class__.__name__
        utils.logMsg("%s %s" % (self.addonName, self.className), msg, int(lvl))

    def setAudioSubsPref(self, audio, subs):
        self.audioPref = audio
        self.subsPref = subs
    
    def hasData(self, data):
        if(data == None or len(data) == 0 or data == "None"):
            return False
        else:
            return True 
    
    def stopAll(self):

        if(len(self.played_information) == 0):
            return 
            
        addonSettings = xbmcaddon.Addon(id='plugin.video.emby')
        self.logMsg("emby Service -> played_information : " + str(self.played_information))

        for item_url in self.played_information:
            data = self.played_information.get(item_url)
            if (data is not None):
                self.logMsg("emby Service -> item_url  : " + item_url)
                self.logMsg("emby Service -> item_data : " + str(data))

                runtime = data.get("runtime")
                currentPosition = data.get("currentPosition")
                item_id = data.get("item_id")
                refresh_id = data.get("refresh_id")
                currentFile = data.get("currentfile")
                type = data.get("Type")

                if(currentPosition != None and self.hasData(runtime)):
                    runtimeTicks = int(runtime)
                    self.logMsg("emby Service -> runtimeticks:" + str(runtimeTicks))
                    percentComplete = (currentPosition * 10000000) / runtimeTicks
                    markPlayedAt = float(90) / 100    

                    self.logMsg("emby Service -> Percent Complete:" + str(percentComplete) + " Mark Played At:" + str(markPlayedAt))
                    if percentComplete < markPlayedAt:
                        # Do not mark as watched
                        self.WINDOW.setProperty('played_skipWatched', 'true')

                    self.stopPlayback(data)
                    
                    offerDelete=False
                    if data.get("Type") == "Episode" and addonSettings.getSetting("offerDeleteTV")=="true":
                        offerDelete = True
                    elif data.get("Type") == "Movie" and addonSettings.getSetting("offerDeleteMovies")=="true":
                        offerDelete = True

                    if percentComplete > .80 and offerDelete == True:
                        return_value = xbmcgui.Dialog().yesno("Offer Delete", "Delete\n" + data.get("currentfile").split("/")[-1] + "\non Emby Server? ")
                        if return_value:
                            # Delete Kodi entry before Emby
                            listItem = [item_id]
                            LibrarySync().removefromDB(listItem, True)
                    
        # Stop transcoding
        if self.WINDOW.getProperty("transcoding%s" % item_id) == "true":
            deviceId = self.clientInfo.getMachineId()
            url = "{server}/mediabrowser/Videos/ActiveEncodings?DeviceId=%s" % deviceId
            self.doUtils.downloadUrl(url, type="DELETE")
            self.WINDOW.clearProperty("transcoding%s" % item_id)
                
        self.played_information.clear()
    
    def stopPlayback(self, data):
        
        self.logMsg("stopPlayback called", 2)
        
        item_id = data.get("item_id")
        currentPosition = data.get("currentPosition")
        positionTicks = int(currentPosition * 10000000)

        url = "{server}/mediabrowser/Sessions/Playing/Stopped"
        
        postdata = {
            'ItemId': item_id,
            'MediaSourceId': item_id,
            'PositionTicks': positionTicks
        } 
            
        self.doUtils.downloadUrl(url, postBody=postdata, type="POST")
    
    def reportPlayback(self):
        
        self.logMsg("reportPlayback Called", 2)
        xbmcplayer = self.xbmcplayer
        
        if not xbmcplayer.isPlaying():
            self.logMsg("reportPlayback: Not playing anything so returning", 0)
            return

        currentFile = xbmcplayer.getPlayingFile()
        data = self.played_information.get(currentFile)

        # only report playback if emby has initiated the playback (item_id has value)
        if data is not None and data.get("item_id") is not None:

            # Get playback information
            item_id = data.get("item_id")
            audioindex = data.get("AudioStreamIndex")
            subtitleindex = data.get("SubtitleStreamIndex")
            playTime = data.get("currentPosition")
            playMethod = data.get("playmethod")
            paused = data.get("paused")
            
            if paused is None:
                paused = False

            # Get playback volume
            volume_query = '{"jsonrpc": "2.0", "method": "Application.GetProperties", "params": {"properties": ["volume","muted"]}, "id": 1}'
            result = xbmc.executeJSONRPC(volume_query)
            result = json.loads(result)
            volume = result.get(u'result').get(u'volume')
            muted = result.get(u'result').get(u'muted')

            postdata = {
                'QueueableMediaTypes': "Video",
                'CanSeek': True,
                'ItemId': item_id,
                'MediaSourceId': item_id,
                'PlayMethod': playMethod,
                'IsPaused': paused,
                'VolumeLevel': volume,
                'IsMuted': muted
            }

            if playTime:
                postdata['PositionTicks'] = int(playTime * 10000000)

            if audioindex:
                postdata['AudioStreamIndex'] = audioindex

            if subtitleindex:
                postdata['SubtitleStreamIndex'] = subtitleindex

            postdata = json.dumps(postdata)
            self.logMsg("Report: %s" % postdata, 2)
            self.ws.sendProgressUpdate(postdata)
    
    def onPlayBackPaused( self ):
        currentFile = xbmc.Player().getPlayingFile()
        self.logMsg("PLAYBACK_PAUSED : " + currentFile,2)
        if(self.played_information.get(currentFile) != None):
            self.played_information[currentFile]["paused"] = "true"
        self.reportPlayback()
    
    def onPlayBackResumed( self ):
        currentFile = xbmc.Player().getPlayingFile()
        self.logMsg("PLAYBACK_RESUMED : " + currentFile,2)
        if(self.played_information.get(currentFile) != None):
            self.played_information[currentFile]["paused"] = "false"
        self.reportPlayback()
    
    def onPlayBackSeek( self, time, seekOffset ):
        self.logMsg("PLAYBACK_SEEK",2)
        # Make position when seeking a bit more accurate
        try:
            playTime = xbmc.Player().getTime()
            currentFile = xbmc.Player().getPlayingFile()
            if(self.played_information.get(currentFile) != None):
                self.played_information[currentFile]["currentPosition"] = playTime
        except: pass
        self.reportPlayback()
        
    def onPlayBackStarted( self ):
        # Will be called when xbmc starts playing a file
        WINDOW = self.WINDOW
        addon = self.addon
        xbmcplayer = self.xbmcplayer
        self.stopAll()
        
        if xbmcplayer.isPlaying():
            
            currentFile = ""
            try:
                currentFile = xbmcplayer.getPlayingFile()
            except: pass
            self.logMsg("onPlayBackStarted: %s" % currentFile, 0)

            playMethod = WINDOW.getProperty(currentFile + "playmethod")

            # Set audio and subtitles automatically
            # Following Emby user preference.
            '''if self.audioPref == "default" and self.subsPref == "default":
                self.logMsg("No Emby user preferences found.", 2)
                # Emby user preferences are not set.
                pass
            elif playMethod == "DirectPlay" or playMethod == "DirectStream":
                # Only currently compatible with DirectPlay.
                # Tested on plugin://, unsure about direct paths.
                self.logMsg("Audio Pref: %s Subtitles Pref: %s" % (self.audioPref, self.subsPref), 1)
                audiotracks = xbmcplayer.getAvailableAudioStreams()
                subs = xbmcplayer.getAvailableSubtitleStreams()
                self.logMsg("%s %s" % (audiotracks, subs), 1)
                defaultsubs = WINDOW.getProperty("%ssubs" % currentFile)

                codecs = [
                    # Possible codecs
                    'und','Stereo','AC3','DTS', '5.1'
                    #'Stereo - Stereo','AC3 5.1', 'DTS 5.1', 'DTS-HD MA 5.1'
                ]

                if len(audiotracks) == 1 and len(subs) == 0:
                    # There's only one audio track and no subtitles
                    xbmcplayer.showSubtitles(False)

                else:
                    # More complex cases
                    codec_intrack = False
                    for codec in codecs:
                        if codec in '\n'.join(audiotracks):
                            codec_intrack = True

                    if self.audioPref in audiotracks:
                        self.logMsg("Door 1", 1)
                        # Audio pref is available
                        index = audiotracks.index(self.audioPref)
                        xbmcplayer.setAudioStream(index)

                        if addon.getSetting('subsoverride') == "true":
                            if self.subsPref in subs:
                                self.logMsg("Door 1.1", 1)
                                # Subs are forced.
                                index = subs.index(self.subsPref)
                                xbmcplayer.setSubtitleStream(index)
                            else:
                                # Use default subs
                                if defaultsubs == "ssa" or defaultsubs == "srt":
                                    # For some reason, Kodi sees SSA as ''
                                    self.logMsg("Door 1.2", 1)
                                    index = subs.index('')
                                    xbmcplayer.setSubtitleStream(index)
                                elif defaultsubs:
                                    self.logMsg("Door 1.3", 1)
                                    index = subs.index(defaultsubs)
                                    xbmcplayer.setSubtitleStream(index)
                        else:  
                            xbmcplayer.showSubtitles(False)

                    elif (len(audiotracks) == 1) and not codec_intrack:
                        self.logMsg("Door 2", 1)
                        # 1. There's one audio track.
                        # 2. The audio is defined as a language.
                        # 3. Audio pref is not available, guaranteed.
                        if self.subsPref in subs:
                            self.logMsg("Door 2.1", 1)
                            # Subs pref is available.
                            index = subs.index(self.subsPref)
                            xbmcplayer.setSubtitleStream(index)
                        else:
                            # Use default subs
                            if defaultsubs == "ssa" or defaultsubs == "srt":
                                # For some reason, Kodi sees SSA as ''
                                self.logMsg("Door 2.2", 1)
                                index = subs.index('')
                                xbmcplayer.setSubtitleStream(index)
                            elif defaultsubs:
                                self.logMsg("Door 2.3", 1)
                                index = subs.index(defaultsubs)
                                xbmcplayer.setSubtitleStream(index)

                    elif len(audiotracks) == 1 and codec_intrack:
                        self.logMsg("Door 3", 1)
                        # 1. There one audio track.
                        # 2. The audio is undefined or a codec.
                        # 3. Audio track is mislabeled.
                        if self.subsPref in subs:
                            # If the subtitle is available, only display
                            # if the setting is enabled.
                            if addon.getSetting('subsoverride') == "true":
                                # Subs are forced.
                                self.logMsg("Door 3.2", 1)
                                index = subs.index(self.subsPref)
                                xbmcplayer.setSubtitleStream(index)
                            else:
                                # Let the user decide, since track is mislabeled.
                                self.logMsg("Door 3.3")
                                xbmcplayer.showSubtitles(False)
                        else:
                            # Use default subs
                            if defaultsubs == "ssa" or defaultsubs == "srt":
                                # For some reason, Kodi sees SSA as ''
                                self.logMsg("Door 3.4", 1)
                                index = subs.index('')
                                xbmcplayer.setSubtitleStream(index)
                            elif defaultsubs:
                                self.logMsg("Door 3.5", 1)
                                index = subs.index(defaultsubs)
                                xbmcplayer.setSubtitleStream(index)
                            else:
                                # Nothing matches, let the user decide.
                                self.logMsg("Door 3.6", 1)
                                xbmcplayer.showSubtitles(False)'''
            
            # we may need to wait until the info is available
            item_id = WINDOW.getProperty(currentFile + "item_id")
            tryCount = 0
            while(item_id == None or item_id == ""):
                xbmc.sleep(500)
                item_id = WINDOW.getProperty(currentFile + "item_id")
                tryCount += 1
                if(tryCount == 20): # try 20 times or about 10 seconds
                    return
            xbmc.sleep(500)
            
            # grab all the info about this item from the stored windows props
            # only ever use the win props here, use the data map in all other places
            runtime = WINDOW.getProperty(currentFile + "runtimeticks")
            refresh_id = WINDOW.getProperty(currentFile + "refresh_id")
            audioindex = WINDOW.getProperty(currentFile + "AudioStreamIndex")
            subtitleindex = WINDOW.getProperty(currentFile + "SubtitleStreamIndex")
            playMethod = WINDOW.getProperty(currentFile + "playmethod")
            itemType = WINDOW.getProperty(currentFile + "type")
            seekTime = WINDOW.getProperty(currentFile + "seektime")
            
            # Get playback volume
            volume_query = '{"jsonrpc": "2.0", "method": "Application.GetProperties", "params": {"properties": ["volume","muted"]}, "id": 1}'
            result = xbmc.executeJSONRPC(volume_query)
            result = json.loads(result)
            volume = result.get(u'result').get(u'volume')
            muted = result.get(u'result').get(u'muted')
            
            if seekTime:
                PlaybackUtils().seekToPosition(int(seekTime))
                seekTime = xbmc.Player().getTime()
            else:
                seekTime = 0

            url = "{server}/mediabrowser/Sessions/Playing"
            postdata = {
                'QueueableMediaTypes': "Video",
                'CanSeek': True,
                'ItemId': item_id,
                'MediaSourceId': item_id,
                'PlayMethod': playMethod,
                'VolumeLevel': volume,
                'PositionTicks': int(seekTime),
                'IsMuted': muted
            }

            if audioindex:
                postdata['AudioStreamIndex'] = audioindex

            if subtitleindex:
                postdata['SubtitleStreamIndex'] = subtitleindex
            
            # Post playback to server
            self.logMsg("Sending POST play started.", 1)
            self.doUtils.downloadUrl(url, postBody=postdata, type="POST")
            
            # save data map for updates and position calls
            data = {
                'runtime': runtime,
                'item_id': item_id,
                'refresh_id': refresh_id,
                'currentfile': currentFile,
                'AudioStreamIndex': audioindex,
                'SubtitleStreamIndex': subtitleindex,
                'playmethod': playMethod,
                'Type': itemType,
                'currentPosition': int(seekTime)
            }
            self.played_information[currentFile] = data
            self.logMsg("ADDING_FILE: %s" % self.played_information, 1)

            # log some playback stats
            if(itemType != None):
                if(self.playStats.get(itemType) != None):
                    count = self.playStats.get(itemType) + 1
                    self.playStats[itemType] = count
                else:
                    self.playStats[itemType] = 1
                    
            if(playMethod != None):
                if(self.playStats.get(playMethod) != None):
                    count = self.playStats.get(playMethod) + 1
                    self.playStats[playMethod] = count
                else:
                    self.playStats[playMethod] = 1
            
            # reset in progress position
            #self.reportPlayback()
            
    def GetPlayStats(self):
        return self.playStats
        
    def onPlayBackEnded( self ):
        # Will be called when xbmc stops playing a file
        self.logMsg("onPlayBackEnded", 0)
        
        #workaround when strm files are launched through the addon - mark watched when finished playing
        #TODO --> mark watched when 95% is played of the file
        WINDOW = xbmcgui.Window( 10000 )
        if WINDOW.getProperty("virtualstrm") != "":
            try:
                id = WINDOW.getProperty("virtualstrm")
                type = WINDOW.getProperty("virtualstrmtype")
                watchedurl = "{server}/mediabrowser/Users/{UserId}/PlayedItems/%s" % id
                self.doUtils.downloadUrl(watchedurl, postBody="", type="POST")
                librarySync.updatePlayCount(id)
            except: pass
        WINDOW.clearProperty("virtualstrm")
            
        self.stopAll()

    def onPlayBackStopped( self ):
        # Will be called when user stops xbmc playing a file
        self.logMsg("onPlayBackStopped", 0)
        self.stopAll()
