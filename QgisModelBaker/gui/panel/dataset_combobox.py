# -*- coding: utf-8 -*-
"""
/***************************************************************************
    begin                :    01.08.2021
    git sha              :    :%H$
    copyright            :    (C) 2021 by Dave Signer
    email                :    avid at opengis ch
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from enum import Enum

from qgis.PyQt.QtWidgets import (
    QWidget,
    QComboBox
)
from qgis.PyQt.QtCore import (
    Qt,
    QSortFilterProxyModel
)
from qgis.PyQt.QtGui import (
    QStandardItemModel,
    QStandardItem
)
from qgis.core import (
    QgsProject,
    QgsDataSourceUri,
    QgsExpressionContextUtils
)

from QgisModelBaker.utils.qt_utils import slugify
from QgisModelBaker.libili2db.ili2dbconfig import Ili2DbCommandConfiguration
from QgisModelBaker.libili2db.globals import DbIliMode
from ...libqgsprojectgen.db_factory.db_simple_factory import DbSimpleFactory
class DatasetSourceModel(QStandardItemModel):
    class Roles(Enum):
        DATASETNAME = Qt.UserRole + 1
        MODEL_TOPIC = Qt.UserRole + 2
        BASKET_TID = Qt.UserRole + 3
        # The SCHEMA_TOPIC_IDENTIFICATOR is a combination of db parameters and the topic
        # This because a dataset is usually valid per topic and db schema
        SCHEMA_TOPIC_IDENTIFICATOR = Qt.UserRole + 4

        def __int__(self):
            return self.value

    def __init__(self):
        super().__init__()
        self.schema_baskets = {}

    def refresh(self):
        self.beginResetModel()
        self.clear()
        for schema_identificator in self.schema_baskets.keys():
            for basket in self.schema_baskets[schema_identificator]:
                item = QStandardItem()
                item.setData(basket['datasetname'], int(Qt.DisplayRole))
                item.setData(basket['datasetname'], int(DatasetSourceModel.Roles.DATASETNAME))
                item.setData(basket['topic'], int(DatasetSourceModel.Roles.MODEL_TOPIC))
                item.setData(basket['basket_t_id'], int(DatasetSourceModel.Roles.BASKET_TID))
                item.setData(f"{schema_identificator}_{slugify(basket['topic'])}", int(DatasetSourceModel.Roles.SCHEMA_TOPIC_IDENTIFICATOR))
                self.appendRow(item)
        self.endResetModel()

    def reload_schema_baskets(self, db_connector, schema_identificator):
        baskets_info = db_connector.get_baskets_info()
        baskets = []
        for record in baskets_info:
            basket = {}
            basket['datasetname'] = record['datasetname']
            basket['topic'] = record['topic']
            basket['basket_t_id'] = record['basket_t_id']
            baskets.append(basket)
        self.schema_baskets[schema_identificator] = baskets
        self.refresh()

    def schema_baskets_loaded(self, schema_identificator):
        return schema_identificator in self.schema_baskets

class DatasetCombobox(QComboBox):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        self.db_simple_factory = DbSimpleFactory()

        self.basket_model = DatasetSourceModel()
        self.filtered_model = QSortFilterProxyModel()
        self.filtered_model.setSourceModel(self.basket_model)
        self.filtered_model.setFilterRole(int(DatasetSourceModel.Roles.SCHEMA_TOPIC_IDENTIFICATOR))
        self.setModel(self.filtered_model)

        self.currentIndexChanged.connect(self.set_basket_tid)

    def set_current_layer(self, layer):
        self.setEnabled(False)
        if not layer or not layer.dataProvider().isValid():
            return

        self.currentIndexChanged.disconnect(self.set_basket_tid)
        source_name = layer.dataProvider().name()
        source = QgsDataSourceUri(layer.dataProvider().dataSourceUri())
        schema_identificator = self.make_schema_identificator(source_name, source)
        layer_model_topic_name = QgsExpressionContextUtils.layerScope(layer).variable('interlis_topic')

        # set the filter of the model according the current uri_identificator
        schema_topic_identificator = f"{schema_identificator}_{slugify(layer_model_topic_name)}"
        self.filtered_model.setFilterFixedString(schema_topic_identificator)

        if not self.basket_model.schema_baskets_loaded(schema_identificator):
            print( 'load ')
            # when no datasets are found we check the database again
            mode = ''
            configuration = Ili2DbCommandConfiguration()
            if source_name == 'postgres':
                mode = DbIliMode.pg
                configuration.dbhost = source.host()
                configuration.dbusr = source.username()
                configuration.dbpwd = source.password()
                configuration.database = source.database()
                configuration.dbschema = source.schema()
            elif source_name == 'ogr':
                mode = DbIliMode.gpkg
                configuration.dbfile = source.uri().split('|')[0].strip()
            elif source_name == 'mssql':
                mode = DbIliMode.mssql
                configuration.dbhost = source.host()
                configuration.dbusr = source.username()
                configuration.dbpwd = source.password()
                configuration.database = source.database()
                configuration.dbschema = source.schema()
                        
            db_factory = self.db_simple_factory.create_factory( mode ) 
            config_manager = db_factory.get_db_command_config_manager(configuration)
            self.basket_model.reload_schema_baskets(db_factory.get_db_connector( config_manager.get_uri(), configuration.dbschema), schema_identificator)

        self.set_index(schema_topic_identificator)
        self.currentIndexChanged.connect(self.set_basket_tid)
        self.setEnabled(True)

    def set_index(self, schema_topic_identificator):
        current_basket_tid = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable(schema_topic_identificator)
        matches = self.filtered_model.match(self.filtered_model.index(0, 0), int(DatasetSourceModel.Roles.BASKET_TID), current_basket_tid, 1, Qt.MatchExactly)
        if matches:
            self.setCurrentIndex(matches[0].row())

    def make_schema_identificator(self, source_name, source):
        if source_name == 'postgres' or source_name == 'mssql':
            return slugify(f'{source.host()}_{source.database()}_{source.schema()}')
        elif source_name == 'ogr':
            return slugify(source.uri().split('|')[0].strip())
        return ''

    def set_basket_tid(self, index ):
        model_index = self.model().index(index,0)
        basket_tid = model_index.data(int(DatasetSourceModel.Roles.BASKET_TID))
        schema_topic_identificator = model_index.data(int(DatasetSourceModel.Roles.SCHEMA_TOPIC_IDENTIFICATOR))
        QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(),schema_topic_identificator,basket_tid)
