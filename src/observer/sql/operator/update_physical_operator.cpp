/* Copyright (c) 2021 OceanBase and/or its affiliates. All rights reserved.
miniob is licensed under Mulan PSL v2.
You can use this software according to the terms and conditions of the Mulan PSL v2.
You may obtain a copy of Mulan PSL v2 at:
         http://license.coscl.org.cn/MulanPSL2
THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
See the Mulan PSL v2 for more details. */

#include "sql/operator/update_physical_operator.h"
#include "storage/table/table.h"
#include "storage/trx/trx.h"

RC UpdatePhysicalOperator::update(Trx *trx)
{
  if (children_.size() != 1 || trx == nullptr) {
    return RC::INTERNAL;
  }
  PhysicalOperator &child = *children_[0];
  RC rc = child.open(trx);
  if (rc != RC::SUCCESS) {
    return rc;
  }
  // Snapshot matching records before changing data or index keys, so newly
  // inserted replacement versions cannot be visited again by this UPDATE.
  vector<Record> records;
  while ((rc = child.next()) == RC::SUCCESS) {
    auto *tuple = dynamic_cast<RowTuple *>(child.current_tuple());
    if (tuple == nullptr) {
      rc = RC::INTERNAL;
      break;
    }
    const Record &source = tuple->record();
    int size = table_->table_meta().record_size();
    char *data = static_cast<char *>(malloc(size));
    if (data == nullptr) {
      rc = RC::NOMEM;
      break;
    }
    memcpy(data, source.data(), size);
    Record record;
    record.set_data_owner(data, size);
    record.set_rid(source.rid());
    records.emplace_back(std::move(record));
  }
  RC close_rc = child.close();
  if (rc != RC::RECORD_EOF) {
    return rc;
  }
  if (close_rc != RC::SUCCESS) {
    return close_rc;
  }
  for (Record &old_record : records) {
    Record new_record = old_record;
    char *destination = new_record.data() + field_.offset();
    // Clear bytes left by a longer old CHAR value.
    memset(destination, 0, field_.len());
    int length = field_.type() == AttrType::CHARS ? std::min(field_.len(), value_.length()) : field_.len();
    memcpy(destination, value_.data(), length);
    rc = trx->update_record(table_, old_record, new_record);
    if (rc != RC::SUCCESS) {
      return rc;
    }
  }
  return RC::SUCCESS;
}
