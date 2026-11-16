/* Copyright (c) 2021 OceanBase and/or its affiliates. All rights reserved.
miniob is licensed under Mulan PSL v2.
You can use this software according to the terms and conditions of the Mulan PSL v2.
You may obtain a copy of Mulan PSL v2 at:
         http://license.coscl.org.cn/MulanPSL2
THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
See the Mulan PSL v2 for more details. */

#pragma once

#include "common/sys/rc.h"
#include "sql/stmt/stmt.h"
#include "storage/field/field_meta.h"

class Table;
class FilterStmt;

class UpdateStmt : public Stmt
{
public:
  UpdateStmt(Table *table, const FieldMeta &field, const Value &value, FilterStmt *filter_stmt);
  ~UpdateStmt() override;
  StmtType type() const override { return StmtType::UPDATE; }
  static RC create(Db *db, const UpdateSqlNode &update_sql, Stmt *&stmt);
  Table *table() const { return table_; }
  const FieldMeta &field() const { return field_; }
  const Value &value() const { return value_; }
  FilterStmt *filter_stmt() const { return filter_stmt_; }

private:
  Table *table_;
  FieldMeta field_;
  Value value_;
  FilterStmt *filter_stmt_;
};
