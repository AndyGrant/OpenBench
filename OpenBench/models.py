# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

from django.db.models import CharField, IntegerField, BooleanField, FloatField
from django.db.models import ForeignKey, DateTimeField, OneToOneField
from django.db.models import CASCADE, PROTECT, Model
from django.contrib.auth.models import User

class Engine(Model):

    name     = CharField(max_length=128)
    source   = CharField(max_length=1024)
    protocol = CharField(max_length=16)
    sha      = CharField(max_length=64)
    bench    = IntegerField(default=0)

    def __str__(self):
        return '{0} ({1})'.format(self.name, self.bench)

class Profile(Model):

    user     = ForeignKey(User, PROTECT, related_name='user')
    games    = IntegerField(default=0)
    tests    = IntegerField(default=0)
    repo     = CharField(max_length=256, blank=True)
    engine   = CharField(max_length=128, blank=True)
    enabled  = BooleanField(default=False)
    approver = BooleanField(default=False)
    updated  = DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.__str__()

class Machine(Model):

    user     = ForeignKey(User, PROTECT, related_name='owner')
    osname   = CharField(max_length=128)
    threads  = IntegerField(default=0)
    mnps     = FloatField(default=0.00)
    updated  = DateTimeField(auto_now=True)
    workload = ForeignKey('Test', PROTECT, related_name='workload', default=1)

    def __str__(self):
        return '{0}-{1} ({2})'.format(self.user.username, self.osname, self.id)

class Result(Model):

    test     = ForeignKey('Test', PROTECT, related_name='test')
    machine  = ForeignKey('Machine', PROTECT, related_name='machine')
    games    = IntegerField(default=0)
    wins     = IntegerField(default=0)
    losses   = IntegerField(default=0)
    draws    = IntegerField(default=0)
    crashes  = IntegerField(default=0)
    timeloss = IntegerField(default=0)
    updated  = DateTimeField(auto_now=True)

    def __str__(self):
        return '{0} {1}'.format(self.test.dev.name, self.machine.__str__())

class Test(Model):

    author      = CharField(max_length=64)
    engine      = CharField(max_length=64)

    dev         = ForeignKey('Engine', PROTECT, related_name='dev')
    base        = ForeignKey('Engine', PROTECT, related_name='base')
    source      = CharField(max_length=1024)

    devoptions  = CharField(max_length=256)
    baseoptions = CharField(max_length=256)

    bookname    = CharField(max_length=32)
    timecontrol = CharField(max_length=16)

    priority    = IntegerField(default=0)
    throughput  = IntegerField(default=0)

    elolower    = FloatField(default=0.0)
    eloupper    = FloatField(default=0.0)
    alpha       = FloatField(default=0.0)
    beta        = FloatField(default=0.0)

    lowerllr    = FloatField(default=0.0)
    currentllr  = FloatField(default=0.0)
    upperllr    = FloatField(default=0.0)

    games       = IntegerField(default=0)
    wins        = IntegerField(default=0)
    draws       = IntegerField(default=0)
    losses      = IntegerField(default=0)

    passed      = BooleanField(default=False)
    failed      = BooleanField(default=False)
    finished    = BooleanField(default=False)
    deleted     = BooleanField(default=False)
    approved    = BooleanField(default=False)

    creation    = DateTimeField(auto_now_add=True)
    updated     = DateTimeField(auto_now=True)

    def __str__(self):
        return '{0} vs {1} @ {2}'.format(self.dev.name, self.base.name, self.timecontrol)

class LogEvent(Model):

    data     = CharField(max_length=256)
    author   = CharField(max_length=64)
    test     = ForeignKey('Test', PROTECT, related_name='test1')
    creation = DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{0} {1} {2}".format(self.author, str(self.test), self.data)
