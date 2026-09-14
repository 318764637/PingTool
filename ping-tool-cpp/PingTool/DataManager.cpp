// DataManager.cpp — 目标数据持久化实现
#include "pch.h"
#include "DataManager.h"

// JSON 格式与 Python 版兼容: ["8.8.8.8","1.1.1.1","baidu.com"]
// 使用手动解析（简单数组格式，不引入第三方 json 库）

std::wstring DataManager::DataPath() {
    wchar_t path[MAX_PATH];
    // 获取 exe 所在目录
    DWORD len = GetModuleFileNameW(nullptr, path, MAX_PATH);
    if (len == 0) return L"targets.json";
    std::wstring full(path, len);
    size_t lastSlash = full.find_last_of(L"\\/");
    if (lastSlash != std::wstring::npos) {
        full = full.substr(0, lastSlash + 1);
    }
    return full + L"targets.json";
}

std::vector<std::wstring> DataManager::Load() {
    std::vector<std::wstring> result;
    std::wstring path = DataPath();

    // 读取文件为 UTF-8 字符串
    FILE* f = _wfopen(path.c_str(), L"rb");
    if (!f) return result;
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    if (size <= 0) { fclose(f); return result; }
    fseek(f, 0, SEEK_SET);

    std::string content(size, '\0');
    fread(&content[0], 1, size, f);
    fclose(f);

    // 手动解析 ["...", "..."] 格式
    size_t start = content.find('[');
    if (start == std::string::npos) return result;

    // 在 UTF-8 字符串中提取每个引号内的目标
    bool inQuote = false;
    std::string item;
    for (size_t i = start + 1; i < content.size(); ++i) {
        char c = content[i];
        if (c == '"') {
            inQuote = !inQuote;
            if (!inQuote && !item.empty()) {
                // 将 UTF-8 item 转为 wstring
                int wlen = MultiByteToWideChar(CP_UTF8, 0, item.c_str(), (int)item.size(), nullptr, 0);
                if (wlen > 0) {
                    std::wstring wstr(wlen, L'\0');
                    MultiByteToWideChar(CP_UTF8, 0, item.c_str(), (int)item.size(), &wstr[0], wlen);
                    result.push_back(std::move(wstr));
                }
                item.clear();
            }
            continue;
        }
        if (inQuote) {
            item += c;
        }
        if (c == ']') break;
    }
    return result;
}

bool DataManager::Save(const std::vector<std::wstring>& targets) {
    std::wstring path = DataPath();

    // 构建 JSON 字符串
    std::string json = "[";
    for (size_t i = 0; i < targets.size(); ++i) {
        if (i > 0) json += ",";
        // 将 wstring 转为 UTF-8
        int len = WideCharToMultiByte(CP_UTF8, 0, targets[i].c_str(), (int)targets[i].size(), nullptr, 0, nullptr, nullptr);
        std::string utf8(len, '\0');
        WideCharToMultiByte(CP_UTF8, 0, targets[i].c_str(), (int)targets[i].size(), &utf8[0], len, nullptr, nullptr);
        json += "\"" + utf8 + "\"";
    }
    json += "]\n";

    FILE* f = _wfopen(path.c_str(), L"wb");
    if (!f) return false;
    fwrite(json.c_str(), 1, json.size(), f);
    fclose(f);
    return true;
}

bool DataManager::Add(const std::wstring& target) {
    if (target.empty()) return false;
    auto targets = Load();
    for (const auto& t : targets) {
        if (t == target) return false; // 已存在
    }
    targets.push_back(target);
    return Save(targets);
}

bool DataManager::Delete(const std::wstring& target) {
    auto targets = Load();
    auto it = std::find(targets.begin(), targets.end(), target);
    if (it == targets.end()) return false;
    targets.erase(it);
    return Save(targets);
}
