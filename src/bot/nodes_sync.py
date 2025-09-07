# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)

# هر چیزی مربوط به نودها را نادیده می‌گیریم تا تداخلی ایجاد نشود.

async def sync_nodes_once(*args, **kwargs):
    logger.info("nodes_sync disabled: sync_nodes_once skipped.")

async def node_health_job(*args, **kwargs):
    logger.info("nodes_sync disabled: node_health_job skipped.")

async def sync_nodes_into_panel(*args, **kwargs):
    logger.info("nodes_sync disabled: sync_nodes_into_panel skipped.")
    return True