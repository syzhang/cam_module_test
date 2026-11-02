// Record IMU, fisheye frames and (optionally) SLAM pose from the camera module.
//
// Every sample is logged with three clocks so stream quality can be analysed afterwards:
//   edge_us   - device clock (microseconds), stamped by the camera itself
//   host_s    - SDK's host-side timestamp (steady_clock seconds, mapped from the edge clock)
//   arrival_s - steady_clock seconds when the callback actually ran in this process
//
// Usage: cam_recorder <out_dir> [seconds] [--no-images] [--slam] [--show] [--save-every N]
// Output: imu.csv, fisheye.csv, pose.csv (with --slam), fisheye/<frame>_<cam>.pgm, meta.txt

#include <cstdint>  // xv-types.h uses std::uint8_t etc. without including this
#include <xv-sdk.h>

#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <vector>

namespace {

std::atomic<bool> g_stop{false};

double now_s() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// Writes fisheye frames to disk on a background thread so callbacks never block on I/O.
class ImageWriter {
public:
    explicit ImageWriter(std::string dir) : dir_(std::move(dir)), thread_([this] { run(); }) {}
    ~ImageWriter() {
        { std::lock_guard<std::mutex> lk(m_); done_ = true; }
        cv_.notify_all();
        thread_.join();
    }
    void push(std::int64_t id, int cam, const xv::GrayScaleImage& img) {
        std::lock_guard<std::mutex> lk(m_);
        if (q_.size() > 2000) { ++dropped_; return; }  // disk can't keep up; count instead of stalling
        q_.push_back({id, cam, img});
        cv_.notify_one();
    }
    std::size_t dropped() const { return dropped_; }

private:
    struct Job { std::int64_t id; int cam; xv::GrayScaleImage img; };
    void run() {
        for (;;) {
            Job job;
            {
                std::unique_lock<std::mutex> lk(m_);
                cv_.wait(lk, [this] { return done_ || !q_.empty(); });
                if (q_.empty()) return;
                job = std::move(q_.front());
                q_.pop_front();
            }
            char name[64];
            std::snprintf(name, sizeof(name), "/%08lld_%d.pgm", static_cast<long long>(job.id), job.cam);
            std::ofstream f(dir_ + name, std::ios::binary);
            f << "P5\n" << job.img.width << " " << job.img.height << "\n255\n";
            f.write(reinterpret_cast<const char*>(job.img.data.get()), job.img.width * job.img.height);
        }
    }
    std::string dir_;
    std::mutex m_;
    std::condition_variable cv_;
    std::deque<Job> q_;
    bool done_ = false;
    std::atomic<std::size_t> dropped_{0};
    std::thread thread_;
};

}  // namespace

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "usage: " << argv[0] << " <out_dir> [seconds] [--no-images] [--slam] [--show] [--save-every N]\n";
        return 1;
    }
    const std::string out = argv[1];
    double seconds = 30;
    bool save_images = true, use_slam = false, show = false;
    int save_every = 1;
    for (int i = 2; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--no-images") save_images = false;
        else if (a == "--slam") use_slam = true;
        else if (a == "--show") show = true;
        else if (a == "--save-every" && i + 1 < argc) save_every = std::max(1, std::atoi(argv[++i]));
        else seconds = std::atof(a.c_str());
    }
    for (std::size_t p = out.find('/', 1); ; p = out.find('/', p + 1)) {  // mkdir -p
        mkdir(out.substr(0, p).c_str(), 0755);
        if (p == std::string::npos) break;
    }
    const std::string img_dir = out + "/fisheye";
    if (save_images) mkdir(img_dir.c_str(), 0755);
    std::signal(SIGINT, [](int) { g_stop = true; });

    xv::setLogLevel(xv::LogLevel::warn);
    auto devices = xv::getDevices(10.);
    if (devices.empty()) {
        std::cerr << "No device found. Is it attached to WSL? (usbipd attach --wsl --busid 1-5)\n";
        return 1;
    }
    auto device = devices.begin()->second;
    if (!device->imuSensor() || !device->fisheyeCameras()) {
        std::cerr << "Device has no IMU or fisheye cameras\n";
        return 1;
    }

    std::ofstream imu_csv(out + "/imu.csv"), fe_csv(out + "/fisheye.csv"), pose_csv;
    if (!imu_csv || !fe_csv) {
        std::cerr << "Cannot write to " << out << "\n";
        return 1;
    }
    imu_csv << "edge_us,host_s,arrival_s,gx,gy,gz,ax,ay,az,temp_k\n";
    fe_csv << "frame,device_id,edge_us,host_s,arrival_s,n_images,width,height,saved\n";
    if (use_slam) {
        pose_csv.open(out + "/pose.csv");
        pose_csv << "edge_us,host_s,arrival_s,x,y,z,qx,qy,qz,qw,confidence\n";
    }
    std::mutex imu_m, fe_m, pose_m, show_m;
    std::shared_ptr<xv::FisheyeImages> latest;
    std::atomic<std::size_t> n_imu{0}, n_fe{0}, n_pose{0};
    std::unique_ptr<ImageWriter> writer;
    if (save_images) writer.reset(new ImageWriter(img_dir));

    device->imuSensor()->registerCallback([&](xv::Imu const& imu) {
        const double t = now_s();
        std::lock_guard<std::mutex> lk(imu_m);
        char line[256];
        std::snprintf(line, sizeof(line), "%lld,%.6f,%.6f,%.6f,%.6f,%.6f,%.5f,%.5f,%.5f,%.2f\n",
                      static_cast<long long>(imu.edgeTimestampUs), imu.hostTimestamp, t,
                      imu.gyro[0], imu.gyro[1], imu.gyro[2], imu.accel[0], imu.accel[1], imu.accel[2], imu.temperature);
        imu_csv << line;
        ++n_imu;
    });

    device->fisheyeCameras()->registerCallback([&](xv::FisheyeImages const& fe) {
        const double t = now_s();
        const std::size_t k = n_fe++;
        const bool save = writer && k % save_every == 0;
        if (save)
            for (std::size_t c = 0; c < fe.images.size(); ++c) writer->push(static_cast<std::int64_t>(k), static_cast<int>(c), fe.images[c]);
        {
            std::lock_guard<std::mutex> lk(fe_m);
            const auto& im = fe.images.empty() ? xv::GrayScaleImage{} : fe.images[0];
            char line[256];
            std::snprintf(line, sizeof(line), "%zu,%lld,%lld,%.6f,%.6f,%zu,%zu,%zu,%d\n", k,
                          static_cast<long long>(fe.id), static_cast<long long>(fe.edgeTimestampUs), fe.hostTimestamp, t,
                          fe.images.size(), im.width, im.height, save ? 1 : 0);
            fe_csv << line;
        }
        if (show) {
            std::lock_guard<std::mutex> lk(show_m);
            latest = std::make_shared<xv::FisheyeImages>(fe);
        }
    });

    if (use_slam && device->slam()) {
        device->slam()->registerCallback([&](xv::Pose const& p) {
            const double t = now_s();
            std::lock_guard<std::mutex> lk(pose_m);
            const auto& tr = p.translation();
            const auto& q = p.quaternion();
            char line[256];
            std::snprintf(line, sizeof(line), "%lld,%.6f,%.6f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.3f\n",
                          static_cast<long long>(p.edgeTimestampUs()), p.hostTimestamp(), t,
                          tr[0], tr[1], tr[2], q[0], q[1], q[2], q[3], p.confidence());
            pose_csv << line;
            ++n_pose;
        });
    }

    device->imuSensor()->start();
    device->fisheyeCameras()->start();
    if (use_slam && device->slam()) device->slam()->start();

    const double t0 = now_s();
    std::cout << "Recording to " << out << " for " << seconds << " s (Ctrl+C to stop early)\n";
    double next_report = t0 + 2;
    while (!g_stop && now_s() - t0 < seconds) {
        if (show) {
            std::shared_ptr<xv::FisheyeImages> fe;
            { std::lock_guard<std::mutex> lk(show_m); fe = latest; }
            if (fe && !fe->images.empty()) {
                std::vector<cv::Mat> tiles;
                for (const auto& im : fe->images)
                    tiles.emplace_back(static_cast<int>(im.height), static_cast<int>(im.width), CV_8UC1,
                                       const_cast<std::uint8_t*>(im.data.get()));
                cv::Mat row;
                cv::hconcat(tiles, row);
                if (row.cols > 1600) cv::resize(row, row, cv::Size(), 1600.0 / row.cols, 1600.0 / row.cols);
                cv::imshow("Fisheye cameras (q to quit)", row);
            }
            const int key = cv::waitKey(15);
            if (key == 'q' || key == 27) break;
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
        if (now_s() >= next_report) {
            const double el = now_s() - t0;
            std::printf("\r%5.1fs  imu %6zu (%.0f Hz)  fisheye %5zu (%.1f fps)  pose %6zu   ", el,
                        n_imu.load(), n_imu / el, n_fe.load(), n_fe / el, n_pose.load());
            std::fflush(stdout);
            next_report += 2;
        }
    }
    const double elapsed = now_s() - t0;

    if (use_slam && device->slam()) device->slam()->stop();
    device->fisheyeCameras()->stop();
    device->imuSensor()->stop();
    const std::size_t img_dropped = writer ? writer->dropped() : 0;
    writer.reset();  // flush pending images
    {
        std::lock_guard<std::mutex> a(imu_m), b(fe_m), c(pose_m);
        imu_csv.close();
        fe_csv.close();
        if (pose_csv.is_open()) pose_csv.close();
    }

    std::ofstream meta(out + "/meta.txt");
    meta << "duration_s=" << elapsed << "\nimu_samples=" << n_imu << "\nfisheye_frames=" << n_fe
         << "\npose_samples=" << n_pose << "\nsave_images=" << save_images << "\nsave_every=" << save_every
         << "\nimages_not_written=" << img_dropped << "\nslam=" << use_slam << "\n";
    meta.close();
    std::printf("\nDone: %.1fs, imu %zu, fisheye %zu, pose %zu, images not written %zu\n", elapsed,
                n_imu.load(), n_fe.load(), n_pose.load(), img_dropped);
    std::fflush(stdout);
    std::_Exit(0);  // SDK teardown can hang under usbip; data is already flushed
}
