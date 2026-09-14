// DataManager.h — 目标数据持久化（与 Python 版 DataManager 等效）
#pragma once
#include "pch.h"

class DataManager {
public:
    static std::vector<std::wstring> Load();
    static bool Save(const std::vector<std::wstring>& targets);
    static bool Add(const std::wstring& target);
    static bool Delete(const std::wstring& target);

private:
    static std::wstring DataPath();
};
