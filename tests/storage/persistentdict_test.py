#
# Copyright 2012-2019 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

from __future__ import absolute_import
from __future__ import division

import pytest

from vdsm.storage import exception as se
from vdsm.storage import persistent


class WriterError(Exception):
    """ Raised while writing or reading """


class UserError(Exception):
    """ Raised by user code inside a transaction """


class MemoryWriter(object):

    def __init__(self, lines=(), fail=False):
        self.lines = list(lines)
        self.fail = fail
        self.version = 0

    def readlines(self):
        if self.fail:
            raise WriterError
        return self.lines[:]

    def writelines(self, lines):
        if self.fail:
            raise WriterError
        self.lines = lines[:]
        self.version += 1


def test_persistent_dict_len():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    assert len(pd) == 0

    pd["key 1"] = "value 1"
    assert len(pd) == 1

    pd["key 2"] = "value 2"
    assert len(pd) == 2


def test_persistent_dict_contains():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    assert "key" not in pd
    pd["key"] = "value"
    assert "key" in pd


def test_persistent_dict_get_good_checksum():
    w = MemoryWriter([
        "key 1=value 1",
        "key 2=value 2",
        "_SHA_CKSUM=ad4e8ffdd89dde809bf1ed700838b590b08a3826",
    ])
    pd = persistent.PersistentDict(w)

    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "value 2"


def test_persistent_dict_get_no_checksum():
    initial_lines = [
        "key 1=value 1",
        "key 2=value 2",
    ]
    w = MemoryWriter(initial_lines)
    pd = persistent.PersistentDict(w)

    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "value 2"

    # Storage not modified by reading.
    assert w.lines == initial_lines


def test_persistent_dict_get_bad_checksum():
    initial_lines = [
        "key 1=value 1",
        "key 2=value 2",
        "_SHA_CKSUM=badchecksum",
    ]
    w = MemoryWriter(initial_lines)
    pd = persistent.PersistentDict(w)

    with pytest.raises(se.MetaDataSealIsBroken):
        pd["key 1"]

    # Storage not modified by reading.
    assert w.lines == initial_lines


def test_persistent_dict_getitem_setitem():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    with pytest.raises(KeyError):
        pd["key"]

    pd["key 1"] = "value 1"
    assert pd["key 1"] == "value 1"

    pd["key 2"] = "value 2"
    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "value 2"

    pd.update({"key 3": "value 3", "key 2": "new value 2"})
    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "new value 2"
    assert pd["key 3"] == "value 3"


def test_persistent_dict_get():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    assert pd.get("key") is None
    pd["key"] = "value"
    assert pd.get("key") == "value"


def test_persistent_dict_del():
    w = MemoryWriter(["key=value"])
    pd = persistent.PersistentDict(w)

    del pd["key"]
    assert "key" not in pd


def test_persistent_dict_del_missing():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    with pytest.raises(KeyError):
        del pd["key"]


def test_persistent_dict_iter():
    w = MemoryWriter(["key 1=1", "key 2=2"])
    pd = persistent.PersistentDict(w)

    assert set(pd) == {"key 1", "key 2"}


def test_persistent_dict_clear():
    w = MemoryWriter([
        "key 1=value 1",
        "key 2=value 2",
        "_SHA_CKSUM=ad4e8ffdd89dde809bf1ed700838b590b08a3826",
    ])
    pd = persistent.PersistentDict(w)

    # Trigger reading from storage.
    pd["key 1"]

    # Clears all keys.
    pd.clear()
    assert "key 1" not in pd
    assert "key 2" not in pd

    # Also flush change to storage (includes checksum).
    assert w.lines == [
        "_SHA_CKSUM=da39a3ee5e6b4b0d3255bfef95601890afd80709"
    ]


def test_persistent_dict_storage():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    # Setting value flush dict to writer.
    pd["key 1"] = "value 1"
    assert w.lines == [
        "key 1=value 1",
        "_SHA_CKSUM=fce57dc690209dc4109d993de9c11d72c8ffd4b6",
    ]
    assert w.version == 1

    # Setting another value flush entire dict again.
    pd["key 2"] = "value 2"
    assert w.lines == [
        "key 1=value 1",
        "key 2=value 2",
        "_SHA_CKSUM=ad4e8ffdd89dde809bf1ed700838b590b08a3826",
    ]
    assert w.version == 2

    # Updating flush entire dict again.
    pd.update({"key 3": "value 3", "key 2": "new value 2"})
    assert w.lines == [
        "key 1=value 1",
        "key 2=new value 2",
        "key 3=value 3",
        "_SHA_CKSUM=96cff78771397697ce609321364aabc818299be8",
    ]
    assert w.version == 3


def test_persistent_transaction():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    # Transaction flushes lines to storage once.
    with pd.transaction():
        pd["key 1"] = "value 1"
        pd["key 2"] = "value 2"

    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "value 2"
    assert w.version == 1


def test_persistent_transaction_nested():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    # Transaction flushes lines to storage once.
    with pd.transaction():
        pd["key 1"] = "value 1"
        with pd.transaction():
            pd["key 2"] = "value 2"

    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "value 2"
    assert w.version == 1


def test_persistent_dict_invalidate():
    w = MemoryWriter([
        "key 1=value 1",
        "key 2=value 2",
        "_SHA_CKSUM=ad4e8ffdd89dde809bf1ed700838b590b08a3826",
    ])
    pd = persistent.PersistentDict(w)

    # Trigger reading from storage.
    assert pd["key 1"] == "value 1"

    # Storage contents changed from another host...
    w.lines = [
        "key 1=value 1",
        "key 2=new value 2",
        "key 3=value 3",
        "_SHA_CKSUM=96cff78771397697ce609321364aabc818299be8",
    ]

    # Return value read before.
    assert pd["key 2"] == "value 2"
    assert "key 3" not in pd

    # Invalidating the dict will cause the next get to read again from storage.
    pd.invalidate()

    assert pd["key 1"] == "value 1"
    assert pd["key 2"] == "new value 2"
    assert pd["key 3"] == "value 3"


def test_persistent_dict_write_fail():
    w = MemoryWriter(fail=True)
    pd = persistent.PersistentDict(w)
    with pytest.raises(WriterError):
        pd["key"] = 1
    assert w.lines == []


@pytest.mark.xfail(reason="nested transaction rollback is broken")
def test_persistent_dict_transaction_user_error():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    # User error during the transaction should abort the entire transaction,
    # otherwise we may leave partial changes on storage.
    with pytest.raises(UserError):
        with pd.transaction():
            pd["key 1"] = 1
            raise UserError

    # Nothing should be written since the transaction was aborted.
    assert w.lines == []


@pytest.mark.xfail(reason="nested transaction rollback is broken")
def test_persistent_dict_nested_transaction_user_error():
    w = MemoryWriter()
    pd = persistent.PersistentDict(w)

    # User error during the transaction should abort the entire transaction,
    # otherwise we may leave partial changes on storage.
    with pytest.raises(UserError):
        with pd.transaction():
            pd["key 1"] = 1
            with pd.transaction():
                pd["key 2"] = 2
                raise UserError

    # Nothing should be written since the transaction was aborted.
    assert w.lines == []


def test_persistent_dict_nested_transaction_write_error():
    w = MemoryWriter(fail=True)
    pd = persistent.PersistentDict(w)

    # Write error will abort the entire transaction.
    with pytest.raises(WriterError):
        with pd.transaction():
            pd["key 1"] = 1
            with pd.transaction():
                pd["key 2"] = 2

    # Nothing should be written as we use failing writer.
    assert w.lines == []
