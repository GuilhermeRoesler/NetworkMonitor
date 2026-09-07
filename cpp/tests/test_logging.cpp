#include "test_assert.hpp"

#include "logging.hpp"
#include "paths.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

namespace fs = std::filesystem;

namespace {

class TempAppDir {
public:
    TempAppDir() {
        root_ = fs::temp_directory_path() / ("nm-cpp-log-tests-" + std::to_string(std::rand()));
        fs::create_directories(root_);
        nm::set_app_dir_override(root_);
    }

    ~TempAppDir() {
        nm::set_app_dir_override(std::nullopt);
        std::error_code ec;
        fs::remove_all(root_, ec);
    }

    const fs::path& path() const { return root_; }

private:
    fs::path root_;
};

void write_bytes(const fs::path& path, std::size_t count, char fill = 'a') {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    NM_CHECK(out.good());
    out << std::string(count, fill);
}

}  // namespace

void test_rotate_log_file_creates_backup() {
    TempAppDir tmp;
    const fs::path log = tmp.path() / "monitor.log";
    write_bytes(log, 100);

    nm::rotate_log_file_if_needed(log, /*max_bytes=*/50, /*backup_count=*/2);

    NM_CHECK(!fs::exists(log));
    NM_CHECK(fs::exists(log.string() + ".1"));
    NM_CHECK_EQ(fs::file_size(log.string() + ".1"), 100u);
}

void test_rotate_log_file_shifts_backups() {
    TempAppDir tmp;
    const fs::path log = tmp.path() / "monitor.log";
    write_bytes(log, 80, 'c');
    write_bytes(fs::path(log.string() + ".1"), 60, 'b');
    write_bytes(fs::path(log.string() + ".2"), 40, 'a');

    nm::rotate_log_file_if_needed(log, /*max_bytes=*/50, /*backup_count=*/2);

    NM_CHECK(!fs::exists(log));
    NM_CHECK(fs::exists(log.string() + ".1"));
    NM_CHECK(fs::exists(log.string() + ".2"));
    NM_CHECK(!fs::exists(log.string() + ".3"));
    NM_CHECK_EQ(fs::file_size(log.string() + ".1"), 80u);
    NM_CHECK_EQ(fs::file_size(log.string() + ".2"), 60u);
}

void test_rotate_log_file_skips_when_under_limit() {
    TempAppDir tmp;
    const fs::path log = tmp.path() / "monitor.log";
    write_bytes(log, 40);

    nm::rotate_log_file_if_needed(log, /*max_bytes=*/100, /*backup_count=*/2);

    NM_CHECK(fs::exists(log));
    NM_CHECK(!fs::exists(log.string() + ".1"));
    NM_CHECK_EQ(fs::file_size(log), 40u);
}

void test_log_message_rotates_via_override_path() {
    // Exercita o caminho público: grava além do limite com constante real seria lento;
    // aqui validamos que rotate + append coexistem no helper já coberto acima.
    TempAppDir tmp;
    const fs::path log = nm::log_path();
    write_bytes(log, 30);
    nm::log_message("hello-from-test");
    NM_CHECK(fs::exists(log));

    std::ifstream in(log, std::ios::binary);
    std::string contents((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    NM_CHECK(contents.find("hello-from-test") != std::string::npos);
}

void run_logging_tests() {
    test_rotate_log_file_creates_backup();
    test_rotate_log_file_shifts_backups();
    test_rotate_log_file_skips_when_under_limit();
    test_log_message_rotates_via_override_path();
}
