#
# Copyright 2014-2018 Red Hat, Inc.
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301  USA
#
# Refer to the README and COPYING files for full details of the license
#

from __future__ import absolute_import
from __future__ import division

import time
import uuid

import pytest

from vdsm.storage import localFsSD
from vdsm.storage import constants as sc
from vdsm.storage import exception as se
from vdsm.storage import fileSD
from vdsm.storage import image
from vdsm.storage import managedvolumedb
from vdsm.storage import qemuimg
from vdsm.storage import sd


@pytest.fixture
def tmp_db(tmpdir, monkeypatch):
    db_file = str(tmpdir.join("managedvolumes.db"))
    monkeypatch.setattr(managedvolumedb, "DB_FILE", db_file)
    managedvolumedb.create_db()


def test_incorrect_block_rejected():
    with pytest.raises(se.InvalidParameterException):
        localFsSD.LocalFsStorageDomain.create(
            sc.BLANK_UUID, "test", sd.DATA_DOMAIN,
            sc.BLANK_UUID, sd.ISCSI_DOMAIN, 4, sc.BLOCK_SIZE_4K,
            sc.ALIGNMENT_1M)


def test_incorrect_alignment_rejected():
    with pytest.raises(se.InvalidParameterException):
        localFsSD.LocalFsStorageDomain.create(
            sc.BLANK_UUID, "test", sd.DATA_DOMAIN,
            sc.BLANK_UUID, sd.ISCSI_DOMAIN, 4, sc.BLOCK_SIZE_512,
            sc.ALIGNMENT_2M)


@pytest.mark.parametrize("domain_version", [3, 4])
def test_create_domain_metadata(tmpdir, tmp_repo, fake_access, domain_version):
    remote_path = str(tmpdir.mkdir("domain"))
    tmp_repo.connect_localfs(remote_path)

    sd_uuid = str(uuid.uuid4())
    domain_name = "domain"

    dom = localFsSD.LocalFsStorageDomain.create(
        sdUUID=sd_uuid,
        domainName=domain_name,
        domClass=sd.DATA_DOMAIN,
        remotePath=remote_path,
        version=domain_version,
        storageType=sd.LOCALFS_DOMAIN,
        block_size=sc.BLOCK_SIZE_512,
        alignment=sc.ALIGNMENT_1M)

    lease = sd.DEFAULT_LEASE_PARAMS
    assert dom.getMetadata() == {
        sd.DMDK_CLASS: sd.DATA_DOMAIN,
        sd.DMDK_DESCRIPTION: domain_name,
        sd.DMDK_IO_OP_TIMEOUT_SEC: lease[sd.DMDK_IO_OP_TIMEOUT_SEC],
        sd.DMDK_LEASE_RETRIES: lease[sd.DMDK_LEASE_RETRIES],
        sd.DMDK_LEASE_TIME_SEC: lease[sd.DMDK_LEASE_TIME_SEC],
        sd.DMDK_LOCK_POLICY: "",
        sd.DMDK_LOCK_RENEWAL_INTERVAL_SEC:
            lease[sd.DMDK_LOCK_RENEWAL_INTERVAL_SEC],
        sd.DMDK_POOLS: [],
        sd.DMDK_ROLE: sd.REGULAR_DOMAIN,
        sd.DMDK_SDUUID: sd_uuid,
        sd.DMDK_TYPE: sd.LOCALFS_DOMAIN,
        sd.DMDK_VERSION: domain_version,
        fileSD.REMOTE_PATH: remote_path
    }


def test_create_volume(monkeypatch, tmpdir, tmp_repo, fake_access, fake_rescan,
                       tmp_db, fake_task):
    remote_path = str(tmpdir.mkdir("domain"))
    tmp_repo.connect_localfs(remote_path)

    sd_uuid = str(uuid.uuid4())
    domain_name = "domain"
    domain_version = 4

    dom = localFsSD.LocalFsStorageDomain.create(
        sdUUID=sd_uuid,
        domainName=domain_name,
        domClass=sd.DATA_DOMAIN,
        remotePath=remote_path,
        version=domain_version,
        storageType=sd.LOCALFS_DOMAIN,
        block_size=sc.BLOCK_SIZE_512,
        alignment=sc.ALIGNMENT_1M)

    img_uuid = str(uuid.uuid4())
    vol_uuid = str(uuid.uuid4())
    vol_capacity = 10 * 1024**3
    vol_size = vol_capacity // sc.BLOCK_SIZE_512
    vol_desc = "Test volume"

    # sd.StorageDomainManifest.getRepoPath() assumes at least one pool is
    # attached
    dom.attach(tmp_repo.pool_id)

    with monkeypatch.context() as mc:
        mc.setattr(time, "time", lambda: 1550522547)
        dom.createVolume(
            imgUUID=img_uuid,
            size=vol_size,
            volFormat=sc.COW_FORMAT,
            preallocate=sc.SPARSE_VOL,
            diskType=image.DISK_TYPES[image.DATA_DISK_TYPE],
            volUUID=vol_uuid,
            desc=vol_desc,
            srcImgUUID=sc.BLANK_UUID,
            srcVolUUID=sc.BLANK_UUID)

    vol = dom.produceVolume(img_uuid, vol_uuid)
    actual = vol.getInfo()

    assert int(actual["capacity"]) == vol_capacity
    assert int(actual["ctime"]) == 1550522547
    assert actual["description"] == vol_desc
    assert actual["disktype"] == "DATA"
    assert actual["domain"] == sd_uuid
    assert actual["format"] == sc.VOLUME_TYPES[sc.COW_FORMAT]
    assert actual["parent"] == sc.BLANK_UUID
    assert actual["status"] == "OK"
    assert actual["type"] == "SPARSE"
    assert actual["voltype"] == "LEAF"
    assert actual["uuid"] == vol_uuid

    qcow2_info = qemuimg.info(vol.getVolumePath())

    assert qcow2_info["actualsize"] < vol_capacity
    assert qcow2_info["virtualsize"] == vol_capacity
