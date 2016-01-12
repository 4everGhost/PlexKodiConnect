# -*- coding: utf-8 -*-

#################################################################################################

import json
import os
import sys
import urlparse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import xbmcplugin

import artwork
import utils
import clientinfo
import downloadutils
import librarysync
import read_embyserver as embyserver
import embydb_functions as embydb
import playlist
import playbackutils as pbutils
import playutils
import api

import PlexAPI

#################################################################################################


def doPlayback(itemid, dbid):
    # Get a first XML to get the librarySectionUUID
    item = PlexAPI.PlexAPI().GetPlexMetadata(itemid)
    # Use that to call the playlist
    playlist = PlexAPI.API(item).GetPlexPlaylist()
    if playlist:
        pbutils.PlaybackUtils(playlist).play(itemid, dbid)
        
    else:
        # No playlist received e.g. when directly playing trailers
        pbutils.PlaybackUtils(item).play(itemid, dbid)

##### DO RESET AUTH #####
def resetAuth():
    # User tried login and failed too many times
    resp = xbmcgui.Dialog().yesno(
                heading="Warning",
                line1=(
                    "Emby might lock your account if you fail to log in too many times. "
                    "Proceed anyway?"))
    if resp == 1:
        utils.logMsg("EMBY", "Reset login attempts.", 1)
        utils.window('emby_serverStatus', value="Auth")
    else:
        xbmc.executebuiltin('Addon.OpenSettings(plugin.video.plexkodiconnect)')

def addDirectoryItem(label, path, folder=True):
    li = xbmcgui.ListItem(label, path=path)
    li.setThumbnailImage("special://home/addons/plugin.video.plexkodiconnect/icon.png")
    li.setArt({"fanart":"special://home/addons/plugin.video.plexkodiconnect/fanart.jpg"})
    li.setArt({"landscape":"special://home/addons/plugin.video.plexkodiconnect/fanart.jpg"})
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=path, listitem=li, isFolder=folder)

def doMainListing():
    
    xbmcplugin.setContent(int(sys.argv[1]), 'files')    
    # Get emby nodes from the window props
    embyprops = utils.window('Emby.nodes.total')
    if embyprops:
        totalnodes = int(embyprops)
        for i in range(totalnodes):
            path = utils.window('Emby.nodes.%s.index' % i)
            if not path:
                path = utils.window('Emby.nodes.%s.content' % i)
            label = utils.window('Emby.nodes.%s.title' % i)
            if path:
                addDirectoryItem(label, path)
    
    # some extra entries for settings and stuff. TODO --> localize the labels
    addDirectoryItem("Network credentials", "plugin://plugin.video.plexkodiconnect/?mode=passwords", False)
    addDirectoryItem("Settings", "plugin://plugin.video.plexkodiconnect/?mode=settings", False)
    addDirectoryItem("Add user to session", "plugin://plugin.video.plexkodiconnect/?mode=adduser", False)
    #addDirectoryItem("Cache all images to Kodi texture cache (advanced)", "plugin://plugin.video.plexkodiconnect/?mode=texturecache")
    addDirectoryItem(
        label="Refresh Emby playlists",
        path="plugin://plugin.video.plexkodiconnect/?mode=refreshplaylist",
        folder=False)
    addDirectoryItem("Perform manual sync", "plugin://plugin.video.plexkodiconnect/?mode=manualsync", False)
    addDirectoryItem(
        label="Repair local database (force update all content)",
        path="plugin://plugin.video.plexkodiconnect/?mode=repair",
        folder=False)
    addDirectoryItem(
        label="Perform local database reset (full resync)",
        path="plugin://plugin.video.plexkodiconnect/?mode=reset",
        folder=False)
    addDirectoryItem(
        label="Sync Emby Theme Media to Kodi",
        path="plugin://plugin.video.plexkodiconnect/?mode=thememedia",
        folder=False)
    
    xbmcplugin.endOfDirectory(int(sys.argv[1]))

##### ADD ADDITIONAL USERS #####
def addUser():

    doUtils = downloadutils.DownloadUtils()
    art = artwork.Artwork()
    clientInfo = clientinfo.ClientInfo()
    deviceId = clientInfo.getDeviceId()
    deviceName = clientInfo.getDeviceName()
    userid = utils.window('emby_currUser')
    dialog = xbmcgui.Dialog()

    # Get session
    url = "{server}/emby/Sessions?DeviceId=%s&format=json" % deviceId
    result = doUtils.downloadUrl(url)
    
    try:
        sessionId = result[0]['Id']
        additionalUsers = result[0]['AdditionalUsers']
        # Add user to session
        userlist = {}
        users = []
        url = "{server}/emby/Users?IsDisabled=false&IsHidden=false&format=json"
        result = doUtils.downloadUrl(url)

        # pull the list of users
        for user in result:
            name = user['Name']
            userId = user['Id']
            if userid != userId:
                userlist[name] = userId
                users.append(name)

        # Display dialog if there's additional users
        if additionalUsers:

            option = dialog.select("Add/Remove user from the session", ["Add user", "Remove user"])
            # Users currently in the session
            additionalUserlist = {}
            additionalUsername = []
            # Users currently in the session
            for user in additionalUsers:
                name = user['UserName']
                userId = user['UserId']
                additionalUserlist[name] = userId
                additionalUsername.append(name)

            if option == 1:
                # User selected Remove user
                resp = dialog.select("Remove user from the session", additionalUsername)
                if resp > -1:
                    selected = additionalUsername[resp]
                    selected_userId = additionalUserlist[selected]
                    url = "{server}/emby/Sessions/%s/Users/%s" % (sessionId, selected_userId)
                    doUtils.downloadUrl(url, postBody={}, type="DELETE")
                    dialog.notification(
                            heading="Success!",
                            message="%s removed from viewing session" % selected,
                            icon="special://home/addons/plugin.video.plexkodiconnect/icon.png",
                            time=1000)

                    # clear picture
                    position = utils.window('EmbyAdditionalUserPosition.%s' % selected_userId)
                    utils.window('EmbyAdditionalUserImage.%s' % position, clear=True)
                    return
                else:
                    return

            elif option == 0:
                # User selected Add user
                for adduser in additionalUsername:
                    try: # Remove from selected already added users. It is possible they are hidden.
                        users.remove(adduser)
                    except: pass

            elif option < 0:
                # User cancelled
                return

        # Subtract any additional users
        utils.logMsg("EMBY", "Displaying list of users: %s" % users)
        resp = dialog.select("Add user to the session", users)
        # post additional user
        if resp > -1:
            selected = users[resp]
            selected_userId = userlist[selected]
            url = "{server}/emby/Sessions/%s/Users/%s" % (sessionId, selected_userId)
            doUtils.downloadUrl(url, postBody={}, type="POST")
            dialog.notification(
                    heading="Success!",
                    message="%s added to viewing session" % selected,
                    icon="special://home/addons/plugin.video.plexkodiconnect/icon.png",
                    time=1000)

    except:
        utils.logMsg("EMBY", "Failed to add user to session.")
        dialog.notification(
                heading="Error",
                message="Unable to add/remove user from the session.",
                icon=xbmcgui.NOTIFICATION_ERROR)

    # Add additional user images
    # always clear the individual items first
    totalNodes = 10
    for i in range(totalNodes):
        if not utils.window('EmbyAdditionalUserImage.%s' % i):
            break
        utils.window('EmbyAdditionalUserImage.%s' % i, clear=True)

    url = "{server}/emby/Sessions?DeviceId=%s" % deviceId
    result = doUtils.downloadUrl(url)
    additionalUsers = result[0]['AdditionalUsers']
    count = 0
    for additionaluser in additionalUsers:
        userid = additionaluser['UserId']
        url = "{server}/emby/Users/%s?format=json" % userid
        result = doUtils.downloadUrl(url)
        utils.window('EmbyAdditionalUserImage.%s' % count,
            value=art.getUserArtwork(result['Id'], 'Primary'))
        utils.window('EmbyAdditionalUserPosition.%s' % userid, value=str(count))
        count +=1

##### THEME MUSIC/VIDEOS #####
def getThemeMedia():

    doUtils = downloadutils.DownloadUtils()
    dialog = xbmcgui.Dialog()
    playback = None

    # Choose playback method
    resp = dialog.select("Playback method for your themes", ["Direct Play", "Direct Stream"])
    if resp == 0:
        playback = "DirectPlay"
    elif resp == 1:
        playback = "DirectStream"
    else:
        return

    library = xbmc.translatePath(
                "special://profile/addon_data/plugin.video.plexkodiconnect/library/").decode('utf-8')
    # Create library directory
    if not xbmcvfs.exists(library):
        xbmcvfs.mkdir(library)

    # Set custom path for user
    tvtunes_path = xbmc.translatePath(
        "special://profile/addon_data/script.tvtunes/").decode('utf-8')
    if xbmcvfs.exists(tvtunes_path):
        tvtunes = xbmcaddon.Addon(id="script.tvtunes")
        tvtunes.setSetting('custom_path_enable', "true")
        tvtunes.setSetting('custom_path', library)
        utils.logMsg("EMBY", "TV Tunes custom path is enabled and set.", 1)
    else:
        # if it does not exist this will not work so warn user
        # often they need to edit the settings first for it to be created.
        dialog.ok(
            heading="Warning",
            line1=(
                "The settings file does not exist in tvtunes. ",
                "Go to the tvtunes addon and change a setting, then come back and re-run."))
        xbmc.executebuiltin('Addon.OpenSettings(script.tvtunes)')
        return
        
    # Get every user view Id
    embyconn = utils.kodiSQL('emby')
    embycursor = embyconn.cursor()
    emby_db = embydb.Embydb_Functions(embycursor)
    viewids = emby_db.getViews()
    embycursor.close()

    # Get Ids with Theme Videos
    itemIds = {}
    for view in viewids:
        url = "{server}/emby/Users/{UserId}/Items?HasThemeVideo=True&ParentId=%s&format=json" % view
        result = doUtils.downloadUrl(url)
        if result['TotalRecordCount'] != 0:
            for item in result['Items']:
                itemId = item['Id']
                folderName = item['Name']
                folderName = utils.normalize_string(folderName.encode('utf-8'))
                itemIds[itemId] = folderName

    # Get paths for theme videos
    for itemId in itemIds:
        nfo_path = xbmc.translatePath(
            "special://profile/addon_data/plugin.video.plexkodiconnect/library/%s/" % itemIds[itemId])
        # Create folders for each content
        if not xbmcvfs.exists(nfo_path):
            xbmcvfs.mkdir(nfo_path)
        # Where to put the nfos
        nfo_path = "%s%s" % (nfo_path, "tvtunes.nfo")

        url = "{server}/emby/Items/%s/ThemeVideos?format=json" % itemId
        result = doUtils.downloadUrl(url)

        # Create nfo and write themes to it
        nfo_file = open(nfo_path, 'w')
        pathstowrite = ""
        # May be more than one theme
        for theme in result['Items']:
            putils = playutils.PlayUtils(theme)
            if playback == "DirectPlay":
                playurl = putils.directPlay()
            else:
                playurl = putils.directStream()
            pathstowrite += ('<file>%s</file>' % playurl.encode('utf-8'))
        
        # Check if the item has theme songs and add them   
        url = "{server}/emby/Items/%s/ThemeSongs?format=json" % itemId
        result = doUtils.downloadUrl(url)

        # May be more than one theme
        for theme in result['Items']:
            putils = playutils.PlayUtils(theme)  
            if playback == "DirectPlay":
                playurl = putils.directPlay()
            else:
                playurl = putils.directStream()
            pathstowrite += ('<file>%s</file>' % playurl.encode('utf-8'))

        nfo_file.write(
            '<tvtunes>%s</tvtunes>' % pathstowrite
        )
        # Close nfo file
        nfo_file.close()

    # Get Ids with Theme songs
    musicitemIds = {}
    for view in viewids:
        url = "{server}/emby/Users/{UserId}/Items?HasThemeSong=True&ParentId=%s&format=json" % view
        result = doUtils.downloadUrl(url)
        if result['TotalRecordCount'] != 0:
            for item in result['Items']:
                itemId = item['Id']
                folderName = item['Name']
                folderName = utils.normalize_string(folderName.encode('utf-8'))
                musicitemIds[itemId] = folderName

    # Get paths
    for itemId in musicitemIds:
        
        # if the item was already processed with video themes back out
        if itemId in itemIds:
            continue
        
        nfo_path = xbmc.translatePath(
            "special://profile/addon_data/plugin.video.plexkodiconnect/library/%s/" % musicitemIds[itemId])
        # Create folders for each content
        if not xbmcvfs.exists(nfo_path):
            xbmcvfs.mkdir(nfo_path)
        # Where to put the nfos
        nfo_path = "%s%s" % (nfo_path, "tvtunes.nfo")
        
        url = "{server}/emby/Items/%s/ThemeSongs?format=json" % itemId
        result = doUtils.downloadUrl(url)

        # Create nfo and write themes to it
        nfo_file = open(nfo_path, 'w')
        pathstowrite = ""
        # May be more than one theme
        for theme in result['Items']: 
            putils = playutils.PlayUtils(theme)
            if playback == "DirectPlay":
                playurl = putils.directPlay()
            else:
                playurl = putils.directStream()
            pathstowrite += ('<file>%s</file>' % playurl.encode('utf-8'))

        nfo_file.write(
            '<tvtunes>%s</tvtunes>' % pathstowrite
        )
        # Close nfo file
        nfo_file.close()

    dialog.notification(
            heading="Emby for Kodi",
            message="Themes added!",
            icon="special://home/addons/plugin.video.plexkodiconnect/icon.png",
            time=1000,
            sound=False)

##### REFRESH EMBY PLAYLISTS #####
def refreshPlaylist():

    lib = librarysync.LibrarySync()
    dialog = xbmcgui.Dialog()
    try:
        # First remove playlists
        utils.deletePlaylists()
        # Refresh views
        lib.refreshViews()
        dialog.notification(
                heading="Emby for Kodi",
                message="Emby playlist refreshed",
                icon="special://home/addons/plugin.video.plexkodiconnect/icon.png",
                time=1000,
                sound=False)
    except Exception as e:
        utils.logMsg("EMBY", "Refresh playlist failed: %s" % e, 1)
        dialog.notification(
            heading="Emby for Kodi",
            message="Emby playlist refresh failed",
            icon=xbmcgui.NOTIFICATION_ERROR,
            time=1000,
            sound=False)

##### BROWSE EMBY CHANNELS #####    
def BrowseChannels(itemid, folderid=None):
    
    _addon_id   =   int(sys.argv[1])
    _addon_url  =   sys.argv[0]
    doUtils = downloadutils.DownloadUtils()
    art = artwork.Artwork()

    xbmcplugin.setContent(int(sys.argv[1]), 'files')
    if folderid:
        url = (
                "{server}/emby/Channels/%s/Items?userid={UserId}&folderid=%s&format=json"
                % (itemid, folderid))
    elif itemid == "0":
        # id 0 is the root channels folder
        url = "{server}/emby/Channels?{UserId}&format=json"
    else:
        url = "{server}/emby/Channels/%s/Items?UserId={UserId}&format=json" % itemid

    result = doUtils.downloadUrl(url)
    try:
        channels = result['Items']
    except TypeError:
        pass
    else:
        for item in channels:

            API = api.API(item)
            itemid = item['Id']
            itemtype = item['Type']
            title = item.get('Name', "Missing Title")
            li = xbmcgui.ListItem(title)

            if itemtype == "ChannelFolderItem":
                isFolder = True
            else:
                isFolder = False

            channelId = item.get('ChannelId', "")
            channelName = item.get('ChannelName', "")

            premieredate = API.getPremiereDate()
            # Process Genres
            genre = API.getGenres()
            # Process UserData
            overlay = 0

            userdata = API.getUserData()
            seektime = userdata['Resume']
            played = userdata['Played']
            if played:
                overlay = 7
            else:
                overlay = 6

            favorite = userdata['Favorite']
            if favorite:
                overlay = 5
            
            playcount = userdata['PlayCount']
            if playcount is None:
                playcount = 0

            # Populate the details list
            details = {

                'title': title,
                'channelname': channelName,
                'plot': API.getOverview(),
                'Overlay': str(overlay),
                'playcount': str(playcount)
            }

            if itemtype == "ChannelVideoItem":
                xbmcplugin.setContent(_addon_id, 'movies')
            elif itemtype == "ChannelAudioItem":
                xbmcplugin.setContent(_addon_id, 'songs')

            # Populate the extradata list and artwork
            pbutils.PlaybackUtils(item).setArtwork(li)
            extradata = {

                'id': itemid,
                'rating': item.get('CommunityRating'),
                'year': item.get('ProductionYear'),
                'premieredate': premieredate,
                'genre': genre,
                'playcount': str(playcount),
                'itemtype': itemtype
            }
            li.setInfo('video', infoLabels=extradata)
            li.setThumbnailImage(art.getAllArtwork(item)['Primary'])
            li.setIconImage('DefaultTVShows.png')

            if itemtype == "Channel":
                path = "%s?id=%s&mode=channels" % (_addon_url, itemid)
                xbmcplugin.addDirectoryItem(handle=_addon_id, url=path, listitem=li, isFolder=True)
            
            elif isFolder:
                path = "%s?id=%s&mode=channelsfolder&folderid=%s" % (_addon_url, channelId, itemid)
                xbmcplugin.addDirectoryItem(handle=_addon_id, url=path, listitem=li, isFolder=True)
            else:
                path = "%s?id=%s&mode=play" % (_addon_url, itemid)
                li.setProperty('IsPlayable', 'true')
                xbmcplugin.addDirectoryItem(handle=_addon_id, url=path, listitem=li)

    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

##### LISTITEM SETUP FOR VIDEONODES #####
def createListItem(item):

    title = item['title']
    li = xbmcgui.ListItem(title)
    li.setProperty('IsPlayable', "true")
    
    metadata = {

        'Title': title,
        'duration': str(item['runtime']/60),
        'Plot': item['plot'],
        'Playcount': item['playcount']
    }

    if "episode" in item:
        episode = item['episode']
        metadata['Episode'] = episode

    if "season" in item:
        season = item['season']
        metadata['Season'] = season

    if season and episode:
        li.setProperty('episodeno', "s%.2de%.2d" % (season, episode))

    if "firstaired" in item:
        metadata['Premiered'] = item['firstaired']

    if "showtitle" in item:
        metadata['TVshowTitle'] = item['showtitle']

    if "rating" in item:
        metadata['Rating'] = str(round(float(item['rating']),1))

    if "director" in item:
        metadata['Director'] = " / ".join(item['director'])

    if "writer" in item:
        metadata['Writer'] = " / ".join(item['writer'])

    if "cast" in item:
        cast = []
        castandrole = []
        for person in item['cast']:
            name = person['name']
            cast.append(name)
            castandrole.append((name, person['role']))
        metadata['Cast'] = cast
        metadata['CastAndRole'] = castandrole

    li.setInfo(type="Video", infoLabels=metadata)  
    li.setProperty('resumetime', str(item['resume']['position']))
    li.setProperty('totaltime', str(item['resume']['total']))
    li.setArt(item['art'])
    li.setThumbnailImage(item['art'].get('thumb',''))
    li.setIconImage('DefaultTVShows.png')
    li.setProperty('dbid', str(item['episodeid']))
    li.setProperty('fanart_image', item['art'].get('tvshow.fanart',''))
    for key, value in item['streamdetails'].iteritems():
        for stream in value:
            li.addStreamInfo(key, stream)
    
    return li

##### GET NEXTUP EPISODES FOR TAGNAME #####    
def getNextUpEpisodes(tagname, limit):
    
    count = 0
    # if the addon is called with nextup parameter,
    # we return the nextepisodes list of the given tagname
    xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
    # First we get a list of all the TV shows - filtered by tag
    query = {

        'jsonrpc': "2.0",
        'id': "libTvShows",
        'method': "VideoLibrary.GetTVShows",
        'params': {

            'sort': {'order': "descending", 'method': "lastplayed"},
            'filter': {
                'and': [
                    {'operator': "true", 'field': "inprogress", 'value': ""},
                    {'operator': "contains", 'field': "tag", 'value': "%s" % tagname}
                ]},
            'properties': ['title', 'studio', 'mpaa', 'file', 'art']
        }
    }
    result = xbmc.executeJSONRPC(json.dumps(query))
    result = json.loads(result)
    # If we found any, find the oldest unwatched show for each one.
    try:
        items = result['result']['tvshows']
    except (KeyError, TypeError):
        pass
    else:
        for item in items:
            if utils.settings('ignoreSpecialsNextEpisodes') == "true":
                query = {

                    'jsonrpc': "2.0",
                    'id': 1,
                    'method': "VideoLibrary.GetEpisodes",
                    'params': {

                        'tvshowid': item['tvshowid'],
                        'sort': {'method': "episode"},
                        'filter': {
                            'and': [
                                {'operator': "lessthan", 'field': "playcount", 'value': "1"},
                                {'operator': "greaterthan", 'field': "season", 'value': "0"}
                        ]},
                        'properties': [
                            "title", "playcount", "season", "episode", "showtitle",
                            "plot", "file", "rating", "resume", "tvshowid", "art",
                            "streamdetails", "firstaired", "runtime", "writer",
                            "dateadded", "lastplayed"
                        ],
                        'limits': {"end": 1}
                    }
                }
            else:
                query = {

                    'jsonrpc': "2.0",
                    'id': 1,
                    'method': "VideoLibrary.GetEpisodes",
                    'params': {

                        'tvshowid': item['tvshowid'],
                        'sort': {'method': "episode"},
                        'filter': {'operator': "lessthan", 'field': "playcount", 'value': "1"},
                        'properties': [
                            "title", "playcount", "season", "episode", "showtitle",
                            "plot", "file", "rating", "resume", "tvshowid", "art",
                            "streamdetails", "firstaired", "runtime", "writer",
                            "dateadded", "lastplayed"
                        ],
                        'limits': {"end": 1}
                    }
                }

            result = xbmc.executeJSONRPC(json.dumps(query))
            result = json.loads(result)
            try:
                episodes = result['result']['episodes']
            except (KeyError, TypeError):
                pass
            else:
                for episode in episodes:
                    li = createListItem(episode)
                    xbmcplugin.addDirectoryItem(
                                handle=int(sys.argv[1]),
                                url=episode['file'],
                                listitem=li)
                    count += 1

            if count == limit:
                break

    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

##### GET INPROGRESS EPISODES FOR TAGNAME #####    
def getInProgressEpisodes(tagname, limit):
    
    count = 0
    # if the addon is called with inprogressepisodes parameter,
    # we return the inprogressepisodes list of the given tagname
    xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
    # First we get a list of all the in-progress TV shows - filtered by tag
    query = {

        'jsonrpc': "2.0",
        'id': "libTvShows",
        'method': "VideoLibrary.GetTVShows",
        'params': {

            'sort': {'order': "descending", 'method': "lastplayed"},
            'filter': {
                'and': [
                    {'operator': "true", 'field': "inprogress", 'value': ""},
                    {'operator': "contains", 'field': "tag", 'value': "%s" % tagname}
                ]},
            'properties': ['title', 'studio', 'mpaa', 'file', 'art']
        }
    }
    result = xbmc.executeJSONRPC(json.dumps(query))
    result = json.loads(result)
    # If we found any, find the oldest unwatched show for each one.
    try:
        items = result['result']['tvshows']
    except (KeyError, TypeError):
        pass
    else:
        for item in items:
            query = {

                'jsonrpc': "2.0",
                'id': 1,
                'method': "VideoLibrary.GetEpisodes",
                'params': {

                    'tvshowid': item['tvshowid'],
                    'sort': {'method': "episode"},
                    'filter': {'operator': "true", 'field': "inprogress", 'value': ""},
                    'properties': [
                        "title", "playcount", "season", "episode", "showtitle", "plot",
                        "file", "rating", "resume", "tvshowid", "art", "cast",
                        "streamdetails", "firstaired", "runtime", "writer",
                        "dateadded", "lastplayed"
                    ]
                }
            }
            result = xbmc.executeJSONRPC(json.dumps(query))
            result = json.loads(result)
            try:
                episodes = result['result']['episodes']
            except (KeyError, TypeError):
                pass
            else:
                for episode in episodes:
                    li = createListItem(episode)
                    xbmcplugin.addDirectoryItem(
                                handle=int(sys.argv[1]),
                                url=episode['file'],
                                listitem=li)
                    count += 1

            if count == limit:
                break

    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

##### GET RECENT EPISODES FOR TAGNAME #####    
def getRecentEpisodes(tagname, limit):
    
    count = 0
    # if the addon is called with recentepisodes parameter,
    # we return the recentepisodes list of the given tagname
    xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
    # First we get a list of all the TV shows - filtered by tag
    query = {

        'jsonrpc': "2.0",
        'id': "libTvShows",
        'method': "VideoLibrary.GetTVShows",
        'params': {

            'sort': {'order': "descending", 'method': "dateadded"},
            'filter': {'operator': "contains", 'field': "tag", 'value': "%s" % tagname},
            'properties': ["title","sorttitle"]
        }
    }
    result = xbmc.executeJSONRPC(json.dumps(query))
    result = json.loads(result)
    # If we found any, find the oldest unwatched show for each one.
    try:
        items = result['result']['tvshows']
    except (KeyError, TypeError):
        pass
    else:
        allshowsIds = set()
        for item in items:
            allshowsIds.add(item['tvshowid'])

        query = {

            'jsonrpc': "2.0",
            'id': 1,
            'method': "VideoLibrary.GetEpisodes",
            'params': {

                'sort': {'order': "descending", 'method': "dateadded"},
                'filter': {'operator': "lessthan", 'field': "playcount", 'value': "1"},
                'properties': [
                    "title", "playcount", "season", "episode", "showtitle", "plot",
                    "file", "rating", "resume", "tvshowid", "art", "streamdetails",
                    "firstaired", "runtime", "cast", "writer", "dateadded", "lastplayed"
                ],
                "limits": {"end": limit}
            }
        }
        result = xbmc.executeJSONRPC(json.dumps(query))
        result = json.loads(result)
        try:
            episodes = result['result']['episodes']
        except (KeyError, TypeError):
            pass
        else:
            for episode in episodes:
                if episode['tvshowid'] in allshowsIds:
                    li = createListItem(episode)
                    xbmcplugin.addDirectoryItem(
                                handle=int(sys.argv[1]),
                                url=episode['file'],
                                listitem=li)
                    count += 1

                if count == limit:
                    break

    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

##### GET EXTRAFANART FOR LISTITEM #####
def getExtraFanArt():
    
    emby = embyserver.Read_EmbyServer()
    art = artwork.Artwork()
    embyId = ""
    
    # Get extrafanart for listitem 
    # will be called by skinhelper script to get the extrafanart
    try:
        # for tvshows we get the embyid just from the path
        if xbmc.getCondVisibility("Container.Content(tvshows) | Container.Content(seasons) | Container.Content(episodes)"):
            itemPath = xbmc.getInfoLabel("ListItem.Path")
            if "plugin.video.emby" in itemPath:
                embyId = itemPath.split("/")[-2]
        else:
            #for movies we grab the emby id from the params
            itemPath = xbmc.getInfoLabel("ListItem.FileNameAndPath")
            if "plugin.video.emby" in itemPath:
                params = urlparse.parse_qs(itemPath)
                embyId = params.get('id')
                if embyId: embyId = embyId[0]
        
        if embyId:
            #only proceed if we actually have a emby id
            utils.logMsg("EMBY", "Requesting extrafanart for Id: %s" % embyId, 0)

            # We need to store the images locally for this to work
            # because of the caching system in xbmc
            fanartDir = xbmc.translatePath("special://thumbnails/emby/%s/" % embyId).decode('utf-8')
            
            if not xbmcvfs.exists(fanartDir):
                # Download the images to the cache directory
                xbmcvfs.mkdirs(fanartDir)
                item = emby.getItem(embyId)
                if item:
                    backdrops = art.getAllArtwork(item)['Backdrop']
                    tags = item['BackdropImageTags']
                    count = 0
                    for backdrop in backdrops:
                        # Same ordering as in artwork
                        tag = tags[count]
                        fanartFile = os.path.join(fanartDir, "fanart%s.jpg" % tag)
                        li = xbmcgui.ListItem(tag, path=fanartFile)
                        xbmcplugin.addDirectoryItem(
                                            handle=int(sys.argv[1]),
                                            url=fanartFile,
                                            listitem=li)
                        xbmcvfs.copy(backdrop, fanartFile) 
                        count += 1               
            else:
                utils.logMsg("EMBY", "Found cached backdrop.", 2)
                # Use existing cached images
                dirs, files = xbmcvfs.listdir(fanartDir)
                for file in files:
                    fanartFile = os.path.join(fanartDir, file)
                    li = xbmcgui.ListItem(file, path=fanartFile)
                    xbmcplugin.addDirectoryItem(
                                            handle=int(sys.argv[1]),
                                            url=fanartFile,
                                            listitem=li)
    except Exception as e:
        utils.logMsg("EMBY", "Error getting extrafanart: %s" % e, 1)
    
    # Always do endofdirectory to prevent errors in the logs
    xbmcplugin.endOfDirectory(int(sys.argv[1]))