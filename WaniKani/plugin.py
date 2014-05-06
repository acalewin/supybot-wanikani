###
# Copyright (c) 2014, Acalewin
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import json
import requests
import datetime

import supybot.utils as utils
import supybot.dbi as dbi
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('WaniKani')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


class WKUser(dbi.Record):
    __fields__ = [
        ('nick', eval),
        ('apikey', eval),
    ]


class WKUserDB(plugins.DbiChannelDB):
    class DB(dbi.DB):
        Record = WKUser

        def add(self, nick, apikey):
            record = self.Record(nick=nick, apikey=apikey)
            super(self.__class__, self).add(record)
            
        def remove(self, nick):
            size = self.size()
            for i in range(1, size+1):
                u = self.get(i)
                if u.nick == nick:
                    self.remove(i)
                    return True
            return False

        def getapikey(self, nick):
            size = self.size()
            for i in range(1, size+1):
                u = self.get(i)
                if u.nick == nick:
                    return u.apikey
            return ''


WKUSERDB = plugins.DB('WaniKani', {'flat': WKUserDB})


class WaniKani(callbacks.Plugin):
    """Add the help for "@plugin help WaniKani" here
    This should describe *how* to use this plugin."""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(WaniKani, self)
        self.__parent.__init__(irc)
        self.db = WKUSERDB()

    def wkadd(self, irc, msg, args, apikey):
        """<apikey>
        Links the API key to the caller's nickname"""
        nick = msg.nick
        channel = msg.args[0]
        if apikey:
            irc.reply('Storing WK API Key %s for user %s' % (nick, apikey))
        else:
            irc.reply('No API Key reported')
        self.db.add(channel, nick, apikey)
    add = wrap(wkadd, ['anything'])

    def WK_getstats(self, apikey, target='total'):
        url = "https://www.wanikani.com/api/user/%s/%s/" % (apikey, 'srs-distribution')
        data = ''
        resp_str = ''
        if not target in ('kanji', 'vocabulary', 'total', 'radicals'):
            return 'Unknown parameter passed in'
        try:
            resp = requests.get(url=url)
            data = json.loads(resp.content)
            data = data['requested_information']
            resp_str = 'appr: %d - guru: %d - mast: %d - en: %d - brnd: %d' % (data['apprentice'][target],
                                                                               data['guru'][target],
                                                                               data['master'][target],
                                                                               data['enlighten'][target],
                                                                               data['burned'][target])
        except:
            resp_str = "Error loading data from WK. Yell at someone."
        return resp_str

    def WK_getkanjistats(self, apikey):
        return self.WK_getstats(apikey, 'kanji')
    
    def WK_getvocabstats(self, apikey):
        return self.WK_getstats(apikey, 'vocabulary')

    def WK_getradicalstats(self, apikey):
        return self.WK_getstats(apikey, 'radicals')

    def WK_getallstats(self, apikey):
        return self.WK_getstats(apikey, 'total')

    def WK_getreviews(self, apikey):
        url = "https://www.wanikani.com/api/user/%s/%s/" % (apikey, 'study-queue')
        try:
            resp = requests.get(url=url)
            data = json.loads(resp.content)
            data = data['requested_information']
            reviews = data['reviews_available']
            nextreview = 'NOW'
            if (reviews == 0):
                nextreview = 'VACATION' if not data['next_review_date'] else \
                             datetime.fromtimestamp(data['next_review_date'])
                if (nextreview != 'VACATION'):
                    nextreview = nextreview.isoformat()
        except:
            return 'Error loading data from WK. Yell at someone'
        return 'L: %d - R: %d - NEXT: %s' % (data['lessons_available'], reviews, nextreview)

    def itemstats(self, irc, msg, args, subset):
        """ [<kanji|radicals|vocab>]
        Returns the item statistics all items or the indicated subset"""

        channel = msg.args[0]
        user = msg.nick
        apikey = self.db.getapikey(channel, user)
        
        if not apikey:
            irc.reply('No API key found for %s' % user)
            return
        if not subset:
            irc.reply(self.WK_getallstats(apikey))
        elif subset.lower() == 'kanji':
            irc.reply(self.WK_getkanjistats(apikey))
        elif subset.lower() == 'vocab':
            irc.reply(self.WK_getvocabstats(apikey))
        elif subset.lower() == 'radicals':
            irc.reply(self.WK_getradicalstats(apikey))
        else:
            irc.reply("you provided a stupid option.")
    itemstats = wrap(itemstats, [optional('anything')])

    def reviews(self, irc, msg, args):
        """ No inputs
        Returns the user's current review count, or time to next review"""
        channel = msg.args[0]
        user = msg.nick
        apikey = self.db.getapikey(channel, user)
        irc.reply(self.WK_getreviews(apikey))
    reviews = wrap(reviews)

    def poll(self, irc, msg):
        pass

Class = WaniKani


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
