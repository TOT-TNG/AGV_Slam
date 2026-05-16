/* 
  + Đào Quang Bình
  + Date 24.2.2026
  + Làm lại mới nhất
  
  --- GIAO THỨC GIAO TIẾP JSON (ARDUINO <-> SERVER/PYTHON) ---
  1. Server gửi xuống (Command):
     - Kế hoạch chạy: 
       {"c":"plan", "d":[{"t":101, "a":5, "v":0}, {"t":102, "a":3, "v":0}]}
       (t: tag/thẻ, a: action/hành động, v: value/giá trị)
     - Lệnh tức thời:
       {"c":"run"}   -> Chạy tiếp
       {"c":"stop"}  -> Dừng khẩn cấp
       {"c":"reset"} -> Khởi động lại

  2. Arduino gửi lên (Status/Request):
     - Trạng thái (gửi định kỳ 500ms):
       {"tag": 101, "status": "auto", "error": "", "action_info": "running"}
     - Yêu cầu (khi bấm nút):
       {"type":"request", "event":"line", "value":1}
       {"type":"request", "event":"station", "value":0}

  --- ACTION CODES (Biến 'a') ---
  1: WAIT_SYS (Chờ hệ thống lệnh)
  2: WAIT_USER (Chờ người dùng bấm nút)
  3: RUN (Chạy dò line)
  4: SPEED (Cài tốc độ, v = tốc độ)
  5: TURN_R (Rẽ phải 90 độ)
  6: TURN_L (Rẽ trái 90 độ)
  11: CLEAR (Xóa lỗi/Reset)
 */
// SERIAL_RX_BUFFER_SIZE áp dụng cho TẤT CẢ 4 UART trên Mega → 4×N bytes SRAM.
// 512: đủ giữ plan ~500 bytes trong lúc delay() HMI (100ms × 115200 baud = 1440 bytes/s)
// KHÔNG tăng lên 1024: 4×1024=4KB + doc/pubDoc/ubuf → vượt 8KB SRAM → doc bị corrupt
#define SERIAL_RX_BUFFER_SIZE 256
#include <Nextion.h>
#include <ArduinoJson.h>
#include <avr/wdt.h>
// Hardware Serial3 (TX3=14, RX3=15) — không bị PID interrupt làm hỏng timing
// Nối dây: Arduino TX3(pin14) → ESP RX | Arduino RX3(pin15) → ESP TX
#define UART_ESP Serial3
void ResetBoard() {
  asm volatile("jmp 0");
}
// Khai bao chan dieu khien toc do-chieu quay, break DC BLDC ZD
/////// NEW KHAI BAO---------------------------------------
#define TIMEOUT 2000
#define MAX_TOPICS 20
#define RFID_TAG "0020"
#define PWM_T 10  // DC trai
#define PWM_P 11  // DC phai
#define CW_T 44   //44 // DAO CHIEU DC TRAI
#define CW_P 45   //45 // DAO CHIEU DC PHAI
#define BREAK12 26
// Dinh nghia cac chan cam bien
#define ss1 A15       //B -1 LED MÉP TRAI
#define ss2 A14       //BR-1
#define ss3 A13       //L-1
#define ss4 A12       //W-1
#define ss5 A11       // GR-1
#define ss6 A10       //B-2
#define ss7 A9        //BR-2
#define ss8 A8        //L-2
#define ss9 A7        //W-2
#define ss10 A6       //GR-2
#define ss11 A5       //B-3
#define ss12 A4       //BR-3
#define ss13 A3       //L-3
#define ss14 4        //B-4
#define ss15 5        //BR-4
#define ss16 2        //L-4 LED MEP PHAI
#define sstoi_0V 24   //chon chieu bat sensor chay toi
#define sstoi_24V 36  //chon chieu bat sensor chay toi
#define sslui_0V 25   //chon chieu bat sensor chay lui
#define sslui_24V 35  //chon chieu bat sensor chay lui
//Dinh nghia cac chan cam bien vat can, cam bien co hang
#define CBVC1 3   // CBVC lidar truoc out 1
#define CBVC2 6   // CBVC lidar truoc out 2
#define CBVC3 7   // CBVC lidar sau out 1
#define CBVC4 8   // CBVC lidar sau out 2
#define CBVC5 49  // dùng quét lúc quay về lidar trc
//#define CBVC6     // dùng quét lúc quay về lidar sau <đang bí input>
#define CB_VACHAM 9  // CAM BIEN VA CHAM truoc/sau
// Dinh nghia cac chan dieu khien nhac,bao pin
#define I_stop 28   //dk loa nhac STOP
#define I_start 27  // dk loa nhac START
#define I_1 33      // dk loa nhac xin cap lieu
//#define do_dungluongpin 49  // giao tiep mach do dung luong pin
// Bật/tắt tính năng giám sát pin yếu.
// Comment dòng dưới nếu AGV KHÔNG lắp cảm biến pin →
//   battery_low = false, battery_blocking = false, xe luôn nhận lệnh bình thường.
//#define ENABLE_BATTERY_SENSOR  // Tạm tắt: chân 37 chưa đấu cảm biến
// ⚠ QUAN TRỌNG: KHÔNG dùng pin 14 (= TX3 / Serial3 TX — UART giao tiếp ESP32)
//   TX3 idle luôn HIGH → digitalRead(14) luôn = HIGH → battery_low luôn true → xe bị chặn!
//   Cắm dây cảm biến vào pin 38 (hoặc bất kỳ pin tự do 22–53).
#define PIN_PIN_YEU 37
//#define dienapsac 48 // dk sac acquy
#define lidar_X0 29  //
#define spare_X1 39  //
#define spare_X2 30  // chân này dùng để rs WiFi. // RS wifi bằng việc set lên mức cao, bình thường là có điện.
#define spare_X3 22  //
#define denbao_RFID 23
#define dieukhien_denxanh 32  //den 3 thap
#define dieukhien_denvang 31  //den 3 thap
#define cambienphat 34        // Điều khiển cảm biến phát
#define nutbam_lui 37         // Nut bam lui xe
#define nutbam_tien 46        // Nut bam tien xe
bool da_an_chaytiep = false;  // nút ấn chạy tiêp
bool battery_low      = false;  // Tín hiệu cảm biến: HIGH = pin yếu (≤20%)
bool battery_blocking = false;  // Chặn lệnh mới: pin yếu + đã về/hoàn thành hành trình
bool waitingForSupply = false;       // Đang chờ xác nhận cấp liệu tại điểm chờ
int  supplyTeamCount = 0;            // Số tổ đang được chọn cấp hàng (server cập nhật qua set_btn_pic)
unsigned long b37BlinkTimer = 0;     // Timer nhấp nháy nút b37
bool b37BlinkState = false;          // Trạng thái hiện tại của b37 (false=pic29, true=pic30)
bool deliveryWaiting = false;        // Đang chờ người dùng bấm b11 tại tổ giao hàng
unsigned long b11BlinkTimer = 0;     // Timer nhấp nháy nút b11
bool b11BlinkState = false;          // Trạng thái hiện tại của b11 (false=pic29, true=pic30)

// ── Off-route detection: phát hiện xe đi sai đường ───────────────────────────
// missionSeenCount > 0: xe đã qua ít nhất 1 thẻ ĐÚNG → 1 thẻ lạ = dừng ngay.
// missionSeenCount = 0: xe chưa xác nhận vị trí    → cần 2 thẻ lạ liên tiếp.
int consecutiveUnknownTags = 0; // Số thẻ lạ liên tiếp (reset khi gặp thẻ đúng)
int missionSeenCount       = 0; // Số thẻ đúng đã đi qua (reset khi nhận plan mới)

// Setup variables:
int serNum0 = 0, serNum1 = 0, serNum2 = 0, serNum3 = 1;
int Sn0 = 0, Sn1 = 0, Sn2 = 0, Sn3 = 0;
int Last_Sn0 = 0, Last_Sn1 = 0, Last_Sn2 = 0, Last_Sn3 = 0;
bool Normal_mode = 1;  // Chế độ line từ bình thường
bool dungQuytrinh = 0;
//Khai bao RFID_JY
char name_arr[21];
char name_arr1[19];
bool Status_phanh = 0;
String input_nhan = "";  // input chờ đọc $1B từ ESP32
//String str;
/////////////////////////////////////////////////////////////
float errorqueotrai = 2;
float errorqueophai = -2;
bool vaokho = 0, vaochuyen1 = 0, vaochuyen2 = 0, vaochuyen3 = 0;  // dac biet tinh den viec xe da vao kho hay chưa
int left_motor_speed = 0;
int right_motor_speed = 0;
bool duytrigiamtoc = 0;
bool duytrigiamtoc2 = 0;
int duytri_queophai = 0;
int duytri_queotrai = 0;
bool trangthai_CBVC1 = 0;
bool trangthai_CBVC2 = 0;
bool trangthai_CBVC3 = 0;
bool trangthai_CBVC4 = 0;
bool trangthai_CBVC5 = 0;
bool errorDoc = 0;
//int k = 0;
bool docthemoi = 0;
bool demthoat = 0;
bool tatvatcan = 0;
bool batLidardai = 0;
bool tatloa = 0;
bool mute = 0;
String state = "toi";
unsigned long conditionMetTime = 0;  // Bien kiem tra thoi gian dut line tu

// PID Variables
float Kp = 7.5, Ki = 0.0002, Kd = 6;
float error = 0, P = 0, I = 0, D = 0, PID_value = 0;
float previous_error = 0, previous_I = 0;
double filtered_error = 0.0;
double previous_PID_value = 0.0;
unsigned long pid_previousTime = 0;
int initial_motor_speed = 200;
int speed_max = 200;
int speed_min = 5;
int speed_ = 200;
bool speedFromSystem = false; // True khi Python đã gửi ACT_SPEED; ưu tiên hơn HMI

//khai bao bien cho HMI
int variable1 = 0;    // Create a variable to have a counter going up by one on each cycle
int counter = 0;      // Create a variable to have a counter for the + and - buttons
int CurrentPage = 0;  // Create a variable to store which page is currently loaded
bool BTstt[80] = { 0 };
bool ChoPhepQuay1 = 0, ChoPhepQuay2 = 0;
bool AGV = 0;  // Khởi tạo xe bận
// khai báo biến
// --- CẤU TRÚC MISSION PLAN (MỚI) ---
struct MissionTask {
  int tag;      // Thẻ RFID cần xử lý
  int action;   // Hành động: 1=WaitSys, 2=WaitUser, 3=Run, 4=Speed, 5=TurnR...
  int value;    // Giá trị đi kèm (ví dụ tốc độ)
};

MissionTask missionPlan[100]; // Lưu tối đa 100 nhiệm vụ (lookahead lớn hơn)
int missionLength = 0;
int currentMissionIndex = 0;
bool isAutoMode = false;     // Chế độ chạy theo Plan
// --- Chống quay 2 lần: lưu thẻ và thời điểm quay gần nhất ---
int   lastTurnTag          = -1;
int   lastTurnMissionIndex = -1; // Index bước trong plan của lần quay gần nhất
int   lastTurnApproachTag  = -1; // prevTag lúc quay — phân biệt RETRY vs quay từ hướng mới
unsigned long lastTurnTime = 0;

// --- Xác nhận bước đã thực hiện (step-done tracking) ---
// Mỗi lần rẽ được thực hiện → lưu vào completedTurns[].
// Khi gặp lại bước đó trong chuỗi lệnh mới (rolling window) → bỏ qua.
// Reset khi AGV quay lại thẻ phía trước (approachTag) của bước đó.
struct CompletedTurn {
  int missionIndex; // Index bước trong plan — phân biệt 2 lần quay cùng tag+action
  int tag;          // Thẻ thực hiện rẽ
  int action;       // ACT_TURN_L hoặc ACT_TURN_R
  int approachTag;  // prevTag khi rẽ (thẻ xe đến từ đó)
};
const int MAX_COMPLETED_TURNS = 10;
CompletedTurn completedTurns[MAX_COMPLETED_TURNS];
int completedTurnsCount = 0;

// --- MÁY TRẠNG THÁI (STATE MACHINE) ---
enum SystemState {
  STATE_IDLE,         // Đứng yên
  STATE_RUNNING,      // Đang chạy dò line (thay cho deba)
  STATE_OBSTACLE,     // Đang dừng chờ vật cản
  STATE_TURNING_L,    // Đang quay trái
  STATE_TURNING_R,    // Đang quay phải
  STATE_WAIT_USER,    // Chờ người dùng bấm nút
  STATE_WAIT_SYS      // Chờ hệ thống server
};
SystemState sysState = STATE_IDLE;
unsigned long stateTimer = 0; // Dùng để đếm thời gian cho các hành động (quay, chờ...)
bool turnPhase1    = false;   // Giai đoạn 1: quay mù theo thời gian (thoát line cũ)
bool turnLineLost  = false;   // Giai đoạn 2: đã thấy ss8/ss9 MẤT line → chờ XUẤT HIỆN lại

// JSON Buffer
StaticJsonDocument<1024> doc; // JSON nhận vào — trên AVR 8-bit: 1024 bytes đủ cho ~25 steps (slot=8B → 128 slots)
unsigned long lastPublishJson = 0;

// --- BIẾN GIAO TIẾP VÀ TRẠNG THÁI MỚI ---
String lastRecvCmdId = ""; // ID của lệnh gần nhất nhận từ App
String pendingEvent = "";  // Sự kiện đang chờ App xác nhận (VD: "arrived", "line_1")
int currentTag = 0;        // Lưu thẻ RFID hiện tại (Last Known Tag), 0 là không có thẻ
int prevTag = 0;           // Lưu thẻ RFID trước đó — dùng để Python phục hồi hướng xe sau khi restart
bool debaManual = false;   // True khi đang chạy lệnh "deba" thủ công từ App — dừng ngay khi gặp thẻ kế tiếp

// Định nghĩa Action Codes (Khớp với Python)
#define ACT_WAIT_SYS 1
#define ACT_WAIT_USER 2
#define ACT_RUN 3
#define ACT_SPEED 4
#define ACT_TURN_R 5
#define ACT_TURN_L 6
#define ACT_DIR_FWD 7
#define ACT_DIR_BWD 8
#define ACT_TURN_L_BWD 9
#define ACT_TURN_R_BWD 10
#define ACT_CLEAR 11
#define ACT_LIDAR_OFF 20  // Tắt cảm biến vật cản (lidar_bank1 — chỉ dừng khi rất gần)
#define ACT_LIDAR_ON  21  // Bật cảm biến vật cản (lidar_bank0 — bình thường)
// Nhạc / Âm thanh (Sound)
#define ACT_NHAC_START    22  // Nhạc khởi hành (nhacstar)
#define ACT_NHAC_STOP     23  // Nhạc dừng xe   (nhacstop)
#define ACT_NHAC_XIN_LIEU 24  // Nhạc xin cấp liệu (nhacxincaplieu)
#define ACT_NHAC_MO_CUA   25  // Nhạc mở cửa   (nhacmocua)
#define ACT_NHAC_XIN_RE   26  // Nhạc xin rẽ   (nhacxinre)
#define ACT_NHAC_TAT      27  // Tắt nhạc      (tatnhac)
// Phanh (Brake)
#define ACT_BRAKE_ON      28  // Đóng phanh — giữ xe không trượt (dongthang)
#define ACT_BRAKE_OFF     29  // Mở phanh   — cho phép di chuyển (mothang)
// Móc hàng (Hook) — stub, chờ code phần cứng
#define ACT_HOOK_RAISE    30  // Nâng móc (nang_moc — stub)
#define ACT_HOOK_LOWER    31  // Hạ móc   (ha_moc   — stub)
// Đèn tháp (Tower Light)
#define ACT_DEN_VANG      32  // Đèn vàng (batden_vang_3thap)
#define ACT_DEN_XANH      33  // Đèn xanh (batden_xanh_3thap)
#define ACT_DEN_TAT       34  // Tắt đèn  (tatden_3thap)
// Trạm sạc
#define ACT_WAIT_CHARGE   35  // Đến trạm sạc: đèn vàng + bật cảm biến phát, chờ lệnh (không loa/nhấp nháy)

// --- NGUYÊN MẪU HÀM (FUNCTION PROTOTYPES) ---
void ResetBoard();
void triggerEvent(String eventName);
void onNewTagDetected(int newTag);
void executeSingleAction(int action, int val); // Thực thi 1 action tức thời (không cần thẻ)
// void sendRequestToServer(String type, int value); // Hàm cũ, đã được thay thế
void publishJson();
void listenJson();
void updateAGV();
void deba();
void mothang();
void dongthang();
void dongthang_kotatRFID();
void chieutien();
void chieului();
void kiemtra_Lidar_dai();
void tat_RFID();
void bat_RFID();
void chieuqueotrai_90();
void chieuqueophai_90();
void dunglai();
void dunglaigap();
void dunglaigap_kotatRFID();
void dunglaimatline();
void batden_vang_3thap();
void batden_xanh_3thap();
void tatden_3thap();
void tocdomacdinh();
void tocdomacdinh_tb();
void datlaitocdo();
void datlaitocdo_tb();
void giamtoc_tutu();
void giamtoc_tutu_kotatRFID();
void giamtoc_gap();
void kiemtraPin();
void vatcan();
void nhacstar();
void nhacstop();
void nhacdenline();
void nhacxincaplieu();
void nhacpinyeu();
void nhacmocua();
void nhacxinre();
void tatnhac();
void giaotiephmi();
void tat_giaotiephmi();
void bat_giaotiephmi();
void guitrangthai_hmi(String guichuoitrangthai_hmi);
void guitrangthai_chuyenhmi(String guichuoitrangthai_hmi, int giatri_lx);
void guithongtinloi_hmi(String guichuoiloi_hmi);
void docrfid();
void kiemtra_docrfid_JY();
void clear_rifd();
void read_sensor_values();
void calculate_pid();
void motor_control();
void tatgiaotiep_ESP();
void batgiaotiep_ESP();
void Cho_tin_hieuESP();
void reset_ESP32();
void Bat_cambienphat();
void Tat_cambienphat();
bool checkObstacle();

void lidar_bank0();
void lidar_bank1();
void nang_moc();   // Stub — nâng móc hàng (chờ code phần cứng)
void ha_moc();     // Stub — hạ móc hàng  (chờ code phần cứng)
void read_sensor_values_trai_phai();
void laygiatri_hmi();
void laygiatrichuyen_hmi();
void hmiSendCommand(const char* cmd); // Đổi tên hàm để tránh trùng với thư viện Nextion

bool ChophepQuay = 0;
NexButton b1 = NexButton(0, 147, "b1");   // Button LINE 1
NexButton b2 = NexButton(0, 148, "b2");   // Button LINE 2
NexButton b5 = NexButton(0, 149, "b5");   // Button LINE 3
NexButton b6 = NexButton(0, 150, "b6");   // Button LINE 4
NexButton b7 = NexButton(0, 151, "b7");   // Button LINE 5
NexButton b9 = NexButton(0, 152, "b9");   // Button LINE 6

NexButton b10 = NexButton(0, 153, "b10"); // Button LINE 7
NexButton b0 = NexButton(0, 154, "b0");   // Button LINE 8
NexButton b14 = NexButton(0, 155, "b14"); // Button LINE 9
NexButton b13 = NexButton(0, 156, "b13"); // Button LINE 10
NexButton b3 = NexButton(0, 161, "b3");     // Button LINE 11
NexButton b12 = NexButton(0, 162, "b12");   // Button LINE 12

NexButton b15 = NexButton(0, 163, "b15");   // Button LINE 13
NexButton b16 = NexButton(0, 164, "b16");   // Button LINE 14
NexButton b17 = NexButton(0, 165, "b17");   // Button LINE 15
NexButton b18 = NexButton(0, 166, "b18");   // Button LINE 16
NexButton b19 = NexButton(0, 167, "b19");   // Button LINE 17
NexButton b20 = NexButton(0, 168, "b20");   // Button LINE 18

NexButton b22 = NexButton(0, 157, "b22");   // Button LINE 19
NexButton b23 = NexButton(0, 158, "b23");   // Button LINE 20
NexButton b24 = NexButton(0, 159, "b24");   // Button LINE 21
NexButton b25 = NexButton(0, 160, "b25");   // Button LINE 22
NexButton b35 = NexButton(0, 169, "b35");   // Button LINE 23
NexButton b36 = NexButton(0, 170, "b36");   // Button LINE 24

NexButton b38 = NexButton(0, 171, "b38");   // Button LINE 25
NexButton b39 = NexButton(0, 172, "b39");   // Button LINE 26
NexButton b40 = NexButton(0, 173, "b40");   // Button LINE 27
NexButton b41 = NexButton(0, 174, "b41");   // Button LINE 28
NexButton b42 = NexButton(0, 175, "b42");   // Button LINE 29
NexButton b43 = NexButton(0, 176, "b43");   // Button LINE 30

NexButton b44 = NexButton(0, 177, "b44");   // Button LINE 31
NexButton b45 = NexButton(0, 178, "b45");   // Button LINE 32
NexButton b46 = NexButton(0, 179, "b46");  // Button LINE 33
NexButton b47 = NexButton(0, 180, "b47");   // Button LINE 34
NexButton b48 = NexButton(0, 181, "b48");   // Button LINE 35
NexButton b49 = NexButton(0, 182, "b49");  // Button LINE 36

NexButton b27 = NexButton(0, 183, "b27");   // Button LINE 31
NexButton b28 = NexButton(0, 184, "b28");   // Button LINE 32
NexButton b29 = NexButton(0, 185, "b29");  // Button LINE 33
NexButton b30 = NexButton(0, 186, "b30");   // Button LINE 34
NexButton b31 = NexButton(0, 187, "b31");   // Button LINE 35
NexButton b32 = NexButton(0, 188, "b32");  // Button LINE 36

NexButton b50 = NexButton(0, 189, "b50");   // Button LINE 31
NexButton b51 = NexButton(0, 190, "b51");   // Button LINE 32
NexButton b52 = NexButton(0, 191, "b52");  // Button LINE 33
NexButton b53 = NexButton(0, 191, "b53");   // Button LINE 34
NexButton b54 = NexButton(0, 193, "b54");   // Button LINE 35
NexButton b55 = NexButton(0, 194, "b55");  // Button LINE 36

NexButton b56 = NexButton(0, 195, "b56");   // Button LINE 31
NexButton b57 = NexButton(0, 196, "b57");   // Button LINE 32
NexButton b58 = NexButton(0, 197, "b58");  // Button LINE 33
NexButton b59 = NexButton(0, 198, "b59");   // Button LINE 34
NexButton b60 = NexButton(0, 199, "b60");   // Button LINE 35
NexButton b61 = NexButton(0, 200, "b61");  // Button LINE 36

NexButton b62 = NexButton(0, 201, "b62");   // Button LINE 31
NexButton b63 = NexButton(0, 202, "b63");   // Button LINE 32
NexButton b64 = NexButton(0, 203, "b64");  // Button LINE 33
NexButton b65 = NexButton(0, 204, "b65");   // Button LINE 34
NexButton b66 = NexButton(0, 205, "b66");   // Button LINE 35
NexButton b67 = NexButton(0, 206, "b67");  // Button LINE 36
// nút bấm (đổ xuống đã xong, từ trên hất lên chưa xong)
NexButton b8 = NexButton(0, 117, "b8");  // Button VE TRAM
NexButton b37 = NexButton(0, 7, "b37");  // Button Cap hang
NexButton b11 = NexButton(0, 5, "b11");  // Button Tiep tuc
NexButton b21 = NexButton(0, 15, "b21");  // Button Tatloa
NexButton b4 = NexButton(0, 4, "b4");  // Button Xóa lỗi

NexText t3 = NexText(0, 143, "t3");  // Text box HIEN THI TRANG THAI AGV
NexText t5 = NexText(0, 145, "t5");  // Text box HIEN THI THONG TIN LOI

NexPage page0 = NexPage(0, 0, "page0");  // Page added as a touch event
NexPage page1 = NexPage(1, 0, "page1");  // Page added as a touch event


// bỏ ko lấy từ value nữa mà lấy từ Number
NexNumber n0 = NexNumber(0, 10, "n0");
NexNumber n1 = NexNumber(0, 11, "n1");
NexNumber n2 = NexNumber(0, 12, "n2");
NexNumber n3 = NexNumber(0, 13, "n3");
NexNumber ln4 = NexNumber(0, 16, "ln4");
NexNumber ln5 = NexNumber(0, 17, "ln5");
NexNumber ln6 = NexNumber(0, 18, "ln6");
NexNumber ln7 = NexNumber(0, 19, "ln7");
NexNumber ln8 = NexNumber(0, 20, "ln8");
NexNumber ln9 = NexNumber(0, 21, "ln9");
NexNumber ln10 = NexNumber(0, 22, "ln10");
NexNumber ln11 = NexNumber(0, 23, "ln11");
NexNumber ln12 = NexNumber(0, 24, "ln12");
NexNumber ln13 = NexNumber(0, 25, "ln13");
NexNumber ln14 = NexNumber(0, 26, "ln14");
NexNumber ln15 = NexNumber(0, 27, "ln15");
NexNumber ln16 = NexNumber(0, 28, "ln16");
NexNumber ln17 = NexNumber(0, 29, "ln17");
NexNumber ln18 = NexNumber(0, 30, "ln18");
NexNumber ln19 = NexNumber(0, 31, "ln19");
NexNumber ln20 = NexNumber(0, 32, "ln20");
NexNumber ln21 = NexNumber(0, 33, "ln21");
NexNumber ln22 = NexNumber(0, 34, "ln22");
NexNumber ln23 = NexNumber(0, 35, "ln23");
NexNumber ln24 = NexNumber(0, 36, "ln24");
NexNumber ln25 = NexNumber(0, 37, "ln25");
NexNumber ln26 = NexNumber(0, 38, "ln26");
NexNumber ln27 = NexNumber(0, 39, "ln27");
NexNumber ln28 = NexNumber(0, 40, "ln28");
NexNumber ln29 = NexNumber(0, 41, "ln29");
NexNumber ln30 = NexNumber(0, 42, "ln30");
NexNumber ln31 = NexNumber(0, 43, "ln31");
NexNumber ln32 = NexNumber(0, 44, "ln32");
NexNumber ln33 = NexNumber(0, 45, "ln33");
NexNumber ln34 = NexNumber(0, 46, "ln34");
NexNumber ln35 = NexNumber(0, 47, "ln35");
NexNumber ln36 = NexNumber(0, 48, "ln36");
NexNumber ln37 = NexNumber(0, 49, "ln37");
NexNumber ln38 = NexNumber(0, 50, "ln38");
NexNumber ln39 = NexNumber(0, 51, "ln39");
NexNumber ln40 = NexNumber(0, 91, "ln40");
NexNumber ln41 = NexNumber(0, 92, "ln41");
NexNumber ln42 = NexNumber(0, 93, "ln42");
NexNumber ln43 = NexNumber(0, 94, "ln43");
NexNumber ln44 = NexNumber(0, 95, "ln44");
NexNumber ln45 = NexNumber(0, 96, "ln45");
NexNumber ln46 = NexNumber(0, 97, "ln46");
NexNumber ln47 = NexNumber(0, 98, "ln47");
NexNumber ln48 = NexNumber(0, 99, "ln48");
NexNumber ln49 = NexNumber(0, 100, "ln49");
NexNumber ln50 = NexNumber(0, 101, "ln50");
NexNumber ln51 = NexNumber(0, 102, "ln51");
NexNumber ln52 = NexNumber(0, 103, "ln52");
NexNumber ln53 = NexNumber(0, 104, "ln53");
NexNumber ln54 = NexNumber(0, 105, "ln54");
NexNumber ln55 = NexNumber(0, 106, "ln55");
NexNumber ln56 = NexNumber(0, 107, "ln56");
NexNumber ln57 = NexNumber(0, 108, "ln57");
NexNumber ln58 = NexNumber(0, 109, "ln58");
NexNumber ln59 = NexNumber(0, 110, "ln59");
NexNumber ln60 = NexNumber(0, 111, "ln60");
NexNumber ln61 = NexNumber(0, 112, "ln61");
NexNumber ln62 = NexNumber(0, 113, "ln62");
NexNumber ln63 = NexNumber(0, 114, "ln63");
// Thêm cái này để viết thành hàm => Bên trong điền các thứ tự nút bấm
const char* buttonNames[] = 
{
  "b1",  "b2",  "b5",  "b6",  "b7",  "b9", 
  "b10", "b0",  "b14", "b13", "b3",  "b12",
  "b15", "b16", "b17", "b18", "b19", "b20",
  "b22", "b23", "b24", "b25", "b35", "b36",
  "b38", "b39", "b40", "b41", "b42", "b43",
  "b44", "b45", "b46", "b47", "b48", "b49",
  "b27", "b28", "b29", "b30", "b31", "b32",
  "b50", "b51", "b52", "b53", "b54", "b55",
  "b56", "b57", "b58", "b59", "b60", "b61",
  "b62", "b63", "b64", "b65", "b66", "b67"
};
NexButton *buttons[65] = 
{
  &b1,  &b2,  &b5,  &b6,  &b7,  &b9,
  &b10, &b0,  &b14, &b13, &b3,  &b12,
  &b15, &b16, &b17, &b18, &b19, &b20, 
  &b22, &b23, &b24, &b25, &b35, &b36,
  &b38, &b39, &b40, &b41, &b42, &b43, 
  &b44, &b45, &b46, &b47, &b48, &b49,
  &b27, &b28, &b29, &b30, &b31, &b32,
  &b50, &b51, &b52, &b53, &b54, &b55, 
  &b56, &b57, &b58, &b59, &b60, &b61, 
  &b62, &b63, &b64, &b65, &b66, &b67
};
uint32_t number0 = 0;  // toc do nhanh
uint32_t number1 = 0;  // toc do cham
uint32_t number2 = 0;  // bat or tat Loa
uint32_t number3 = 0;  // toc do trung binh

uint32_t L[80]={0};
// Danh sách đối tượng cần nexLoop theo dõi
NexTouch *nex_listen_list[] = 
{
  // Các nút line
  &b1,  &b2,  &b5,  &b6,  &b7,  &b9,
  &b10, &b0,  &b14, &b13, &b3,  &b12,
  &b15, &b16, &b17, &b18, &b19, &b20, 
  &b22, &b23, &b24, &b25, &b35, &b36,
  &b38, &b39, &b40, &b41, &b42, &b43, 
  &b44, &b45, &b46, &b47, &b48, &b49,
  &b27, &b28, &b29, &b30, &b31, &b32,
  &b50, &b51, &b52, &b53, &b54, &b55, 
  &b56, &b57, &b58, &b59, &b60, &b61, 
  &b62, &b63, &b64, &b65, &b66, &b67,

  // Các nút chức năng đặc biệt
  &b4, &b8, &b11, &b21, &b37,

  // Các tham số dạng số
  &n0, &n1, &n2, &n3,

  // Các line trạng thái
  &ln4, &ln5, &ln6, &ln7, &ln8,
  &ln9, &ln10, &ln11, &ln12, &ln13,
  &ln14, &ln15, &ln16, &ln17, &ln18,
  &ln19, &ln20, &ln21, &ln22, &ln23,
  &ln24, &ln25, &ln26, &ln27, &ln28,
  &ln29, &ln30, &ln31, &ln32, &ln33,
  &ln34, &ln35, &ln36, &ln37, &ln38,
  &ln39, &ln40, &ln41, &ln42, &ln43,
  &ln44, &ln45, &ln46, &ln47, &ln48,
  &ln49, &ln50, &ln51, &ln52, &ln53,
  &ln54, &ln55, &ln56, &ln57, &ln58,
  &ln59, &ln60, &ln61, &ln62, &ln63,

  // Trang hiển thị
  &page0,
  &page1,

  NULL
};
void b4PushCallback(void *ptr)  // Press event for button b4 reset
{
  //Serial2.print("@reset#");
  delay(50);
  tatnhac();
  ResetBoard();
}
void lineButtonPushCallback(void *ptr)
{
  NexButton *btn = (NexButton *)ptr;
  int index = -1;
  for (int i = 0; i < 64; i++)
  {
    if (buttons[i] == btn) {
      index = i + 1;  // line 1–60
      break;
    }
  }
  if (index == -1 || index > 60) return;

  // Arduino tự quyết định màu nút — không cần server gửi lại
  // pic=28: đã chọn tổ | pic=27: bỏ chọn tổ
  char hcmd[24];
  if (BTstt[index] == 0) {
    BTstt[index] = 1;
    supplyTeamCount++;
    snprintf(hcmd, sizeof(hcmd), "%s.pic=28", buttonNames[index - 1]);
  } else {
    BTstt[index] = 0;
    if (supplyTeamCount > 0) supplyTeamCount--;
    snprintf(hcmd, sizeof(hcmd), "%s.pic=27", buttonNames[index - 1]);
  }
  hmiSendCommand(hcmd);
  Serial.print(F("[BTN] line ")); Serial.print(index);
  Serial.print(F(" → ")); Serial.print(BTstt[index] ? "chon" : "bo chon");
  Serial.print(F(" supplyTeamCount=")); Serial.println(supplyTeamCount);

  // Vẫn gửi event lên server để cập nhật selected_targets (dùng khi routing)
  triggerEvent("line_" + String(index));
  delay(25);
}
void b8PushCallback(void *ptr)  // Press event for button b8 ve tram
{
  // Gửi yêu cầu về trạm lên Server
  triggerEvent("station");
  hmiSendCommand("b8.pic=40");
}
void b11PushCallback(void *ptr)  // Press event for button b11 tiep tuc
{
  tatnhac();
  if (deliveryWaiting) {
    // Tại tổ giao hàng: dừng nhấp nháy, báo hệ thống xong — server quyết định tiếp theo
    deliveryWaiting = false;
    hmiSendCommand("b11.pic=37");
    // Tăng index qua ACT_WAIT_USER để tránh vòng lặp khi server gửi "run" thay vì plan mới
    // (Nếu server gửi plan mới thì currentMissionIndex sẽ bị reset về 0 — an toàn)
    if (currentMissionIndex < missionLength &&
        missionPlan[currentMissionIndex].action == ACT_WAIT_USER) {
      currentMissionIndex++;
    }
    isAutoMode = true;             // Cho phép plan mới hoặc lệnh "run" hoạt động ngay
    sysState = STATE_WAIT_SYS;     // Chờ lệnh từ server (không tự chạy)
    triggerEvent("continue");      // Server: tổ tiếp gần nhất hoặc về sạc
  } else {
    // WAIT_USER thông thường: gửi tín hiệu và tự chạy tiếp
    // isAutoMode đã bị set false bởi ACT_WAIT_USER → phải set lại TRƯỚC khi deba()
    triggerEvent("continue");
    if (currentMissionIndex < missionLength &&
        missionPlan[currentMissionIndex].action == ACT_WAIT_USER) {
      currentMissionIndex++;
    }
    isAutoMode = true;
    deba();  // Mở phanh + bật RFID + STATE_RUNNING
  }
}
void b21PushCallback(void *ptr)  // Press event for button b21 tat loa
{
  delay(25);
  tatloa = 1;
}
void b37PushCallback(void *ptr)  // Press event for button b37 Cap lieu - xác nhận cấp liệu
{
  if (waitingForSupply) {
    tatnhac();
    waitingForSupply = false;
    hmiSendCommand("b37.pic=29");
    // Tăng index qua ACT_WAIT_SYS để tránh vòng lặp khi server gửi "run" thay vì plan mới
    if (currentMissionIndex < missionLength &&
        missionPlan[currentMissionIndex].action == ACT_WAIT_SYS) {
      currentMissionIndex++;
    }
    isAutoMode = true;                  // Cho phép plan mới hoặc lệnh "run" hoạt động ngay
    triggerEvent("continue");           // Xin hệ thống cho đi tiếp
  }
}
// Page change event:
void page0PushCallback(void *ptr)  //
{
  CurrentPage = 0;  // Set variable as 0 so from now on arduino knows page 0 is loaded on the display
  //Serial.write("ok");
  // End of press event
}
void page1PushCallback(void *ptr)  // If page 1 is loaded on the display, the following is going to execute:
{
  CurrentPage = 1;  // Set variable as 1 so from now on arduino knows page 1 is loaded on the display
}  // End of press event
// hàm xử lý sự kiện
/////////////////////////////////////////////////////////////////
void laygiatri_hmi() {
  n0.getValue(&number0);
  Serial.print("Value 0: ");
  Serial.println(number0);
  if (!speedFromSystem) {
    speed_ = number0; // Chỉ dùng tốc độ HMI nếu Python chưa gửi ACT_SPEED
    speed_max = min((int)(speed_ + 30), 255);
  }
  // Đọc giá trị từ biến va1
  n1.getValue(&number1);
  Serial.print("Value 1: ");
  Serial.println(number1);
  // Đọc giá trị từ biến va1
  n2.getValue(&number2);
  Serial.print("Value 2: ");
  Serial.println(number2);
  // Đọc giá trị từ biến va1
  n3.getValue(&number3);
  Serial.print("Value 3: ");
  Serial.println(number3);
  speed_min = 5;
}

void laygiatrichuyen_hmi()
{
  //lấy tt line 
  ln4.getValue(&L[1]);
  ln5.getValue(&L[2]);
  ln6.getValue(&L[3]);
  ln7.getValue(&L[4]);
  ln8.getValue(&L[5]);
  ln9.getValue(&L[6]);
  ln10.getValue(&L[7]);
  ln11.getValue(&L[8]);
  ln12.getValue(&L[9]);
  ln13.getValue(&L[10]);
  ln14.getValue(&L[11]);
  ln15.getValue(&L[12]);
  ln16.getValue(&L[13]);
  ln17.getValue(&L[14]);
  ln18.getValue(&L[15]);
  ln19.getValue(&L[16]);
  ln20.getValue(&L[17]);
  ln21.getValue(&L[18]);
  ln22.getValue(&L[19]);
  ln23.getValue(&L[20]);
  ln24.getValue(&L[21]);
  ln25.getValue(&L[22]);
  ln26.getValue(&L[23]);
  ln27.getValue(&L[24]);
  ln28.getValue(&L[25]);
  ln29.getValue(&L[26]);
  ln30.getValue(&L[27]);
  ln31.getValue(&L[28]);
  ln32.getValue(&L[29]);
  ln33.getValue(&L[30]);
  ln34.getValue(&L[31]);
  ln35.getValue(&L[32]);
  ln36.getValue(&L[33]);
  ln37.getValue(&L[34]);
  ln38.getValue(&L[35]);
  ln39.getValue(&L[36]);
  ln40.getValue(&L[37]);
  ln41.getValue(&L[38]);
  ln42.getValue(&L[39]);
  ln43.getValue(&L[40]);
  ln44.getValue(&L[41]);
  ln45.getValue(&L[42]);
  ln46.getValue(&L[43]);
  ln47.getValue(&L[44]);
  ln48.getValue(&L[45]);
  ln49.getValue(&L[46]);
  ln50.getValue(&L[47]);
  ln51.getValue(&L[48]);
  ln52.getValue(&L[49]);
  ln53.getValue(&L[50]);
  ln54.getValue(&L[51]);
  ln55.getValue(&L[52]);
  ln56.getValue(&L[53]);
  ln57.getValue(&L[54]);
  ln58.getValue(&L[55]);
  ln59.getValue(&L[56]);
  ln60.getValue(&L[57]);
  ln61.getValue(&L[58]);
  ln62.getValue(&L[59]);
  ln63.getValue(&L[60]);
}

// --- HÀM GỬI LỆNH XUỐNG MÀN HÌNH NEXTION ---
void hmiSendCommand(const char* cmd) {
  Serial2.print(cmd);
  Serial2.write(0xFF);
  Serial2.write(0xFF);
  Serial2.write(0xFF);
}

// --- HÀM GIAO TIẾP JSON MỚI ---

// Hàm kích hoạt một sự kiện để gửi lên App (Cơ chế chờ ACK)
void triggerEvent(String eventName) {
  pendingEvent = eventName;
  Serial.println("Triggered Event: " + pendingEvent);
  publishJson(); // Gửi ngay lập tức để App nhận được nhanh nhất
}

// Hàm được gọi khi có thẻ RFID mới được phát hiện
void onNewTagDetected(int newTag) {
  if (currentTag != newTag) {
    prevTag = currentTag;  // Lưu thẻ cũ trước khi cập nhật
    currentTag = newTag;
    Serial.println("New Tag Detected: " + String(currentTag) + " (prev=" + String(prevTag) + ")");

    // ── Step-done invalidation: khi gặp thẻ = approachTag của 1 turn đã hoàn thành,
    // có nghĩa là xe quay lại phía trước → xóa turn đó để cho phép thực hiện lại ──
    for (int i = completedTurnsCount - 1; i >= 0; i--) {
      if (completedTurns[i].approachTag == newTag) {
        Serial.print(F("[TURN-RESET] The "));
        Serial.print(newTag);
        Serial.print(F(" = approach -> re-enable turn at tag "));
        Serial.println(completedTurns[i].tag);
        // Xóa entry này (dịch các entry sau lên)
        for (int j = i; j < completedTurnsCount - 1; j++) {
          completedTurns[j] = completedTurns[j + 1];
        }
        completedTurnsCount--;
      }
    }

    // ── Off-route detection (chỉ khi đang chạy auto có plan) ──────────────
    if (isAutoMode && missionLength > 0) {
      bool tagInPlan = false;
      for (int i = 0; i < missionLength; i++) {
        if (missionPlan[i].tag == newTag) { tagInPlan = true; break; }
      }
      if (tagInPlan) {
        // Thẻ đúng plan → reset bộ đếm lạ, tăng số thẻ đúng đã xác nhận
        consecutiveUnknownTags = 0;
        missionSeenCount++;
      } else {
        // Thẻ LẠ — không nằm trong plan
        consecutiveUnknownTags++;
        // Ngưỡng dừng:
        //   missionSeenCount > 0 → đã xác nhận đúng đường → 1 thẻ lạ = dừng ngay
        //   missionSeenCount = 0 → chưa biết vị trí      → cần 2 thẻ lạ liên tiếp
        int threshold = (missionSeenCount > 0) ? 1 : 2;
        Serial.println("[OFF-ROUTE] The la #" + String(consecutiveUnknownTags)
                       + "/" + String(threshold) + " tag=" + String(newTag));
        if (consecutiveUnknownTags >= threshold) {
          isAutoMode  = false;
          debaManual  = false;
          sysState    = STATE_IDLE;
          dunglaigap();
          consecutiveUnknownTags = 0;
          Serial.println("[OFF-ROUTE] DUNG KHAN CAP! Xin he thong dinh tuyen lai.");
          triggerEvent("off_route");
          publishJson();
          return;  // Thoát ngay, không publishJson() lần 2 bên dưới
        }
      }
    }

    // Lệnh DEBA thủ công: dừng ngay khi quét được thẻ kế tiếp
    if (debaManual) {
      debaManual  = false;
      isAutoMode  = false;
      sysState    = STATE_IDLE;  // QUAN TRỌNG: tắt STATE_RUNNING trước, rồi mới dunglaigap()
      dunglaigap();              // nếu không set IDLE, updateAGV() bật lại motor ngay vòng sau
      Serial.println("[DEBA MANUAL] Dung tai the " + String(currentTag));
    }

    // Dừng ngay khi thẻ không có trong plan còn lại:
    // → Xảy ra khi server chưa gửi plan kịp (MQTT latency).
    // → Xe dừng tại thẻ hiện tại, chờ plan mới đến; currentTag vẫn giữ nguyên
    //   nên khi plan đến và có tag này, sẽ execute ngay lập tức.
    if (isAutoMode && sysState == STATE_RUNNING) {
      bool foundInPlan = false;
      for (int i = currentMissionIndex; i < missionLength; i++) {
        if (missionPlan[i].tag == newTag) { foundInPlan = true; break; }
      }
      if (!foundInPlan) {
        sysState = STATE_IDLE;
        dunglaigap();
        Serial.println("[WAIT-PLAN] The " + String(newTag) + " chua trong plan - dung cho plan moi");
      }
    }

    // Gửi ngay lập tức để App cập nhật vị trí tức thời
    publishJson();
  }
}

void publishJson() {
  // VDA5050 v2.0.0: headerId/timestamp/version/manufacturer/serialNumber được thêm bởi ESP32
  static StaticJsonDocument<1024> pubDoc;  // publish: cấu trúc cố định, ~600 bytes thực tế
  pubDoc.clear();

  // ── VDA5050 State fields ──────────────────────────────────────────────────
  // Vị trí: không có encoder → dùng tag RFID làm lastNodeId (VDA5050 §6.6)
  pubDoc["lastNodeId"]         = String(currentTag);
  pubDoc["lastNodeSequenceId"] = (int)currentMissionIndex;
  pubDoc["orderId"]            = lastRecvCmdId;  // ID của plan đang thực hiện

  // operatingMode: AUTOMATIC / SEMIAUTOMATIC (đang quay) / MANUAL
  if (!isAutoMode)
    pubDoc["operatingMode"] = "MANUAL";
  else if (sysState == STATE_TURNING_L || sysState == STATE_TURNING_R)
    pubDoc["operatingMode"] = "SEMIAUTOMATIC";
  else
    pubDoc["operatingMode"] = "AUTOMATIC";

  // driving: đang di chuyển vật lý (chạy hoặc quay)
  pubDoc["driving"] = (sysState == STATE_RUNNING ||
                       sysState == STATE_TURNING_L ||
                       sysState == STATE_TURNING_R);
  // paused: dừng chủ động chờ lệnh (không phải dừng khẩn cấp)
  pubDoc["paused"]  = (sysState == STATE_WAIT_SYS || sysState == STATE_WAIT_USER);
  pubDoc["newBaseRequest"] = false; // Rolling segment do Python quản lý

  // errors[]: mảng lỗi theo VDA5050 §6.6.8
  JsonArray errors = pubDoc.createNestedArray("errors");
  if (tatvatcan) {
    JsonObject e0 = errors.createNestedObject();
    e0["errorType"]        = "OBSTACLE";
    e0["errorLevel"]       = "WARNING";
    e0["errorDescription"] = "Obstacle detected by sensor";
  }

  // safetyState: VDA5050 §6.6.9
  JsonObject safety = pubDoc.createNestedObject("safetyState");
  safety["eStop"]          = (bool)(!isAutoMode && sysState == STATE_IDLE);
  safety["fieldViolation"] = (bool)tatvatcan;

  // nodeStates[]: toàn bộ node còn lại trong plan (VDA5050 §6.6.3)
  // Python lookahead gửi n node (cấu hình được) → Arduino phản ánh đầy đủ
  JsonArray nodeStates = pubDoc.createNestedArray("nodeStates");
  int nsEnd = min(missionLength, currentMissionIndex + 5);   // tối đa 5 node
  for (int ni = currentMissionIndex; ni < nsEnd; ni++) {
    JsonObject ns = nodeStates.createNestedObject();
    ns["nodeId"]     = String(missionPlan[ni].tag);
    ns["sequenceId"] = ni;
    ns["released"]   = true;
  }

  // ── batteryState (VDA5050 §6.6.5) ───────────────────────────────────────
#ifdef ENABLE_BATTERY_SENSOR
  // Cảm biến digital PIN_PIN_YEU: LOW = pin khỏe (>25%), HIGH = pin yếu (<=25%)
  battery_low = (digitalRead(PIN_PIN_YEU) == HIGH);
#endif
  JsonObject batt = pubDoc.createNestedObject("batteryState");
  batt["batteryCharge"]  = battery_low ? 20 : 80;  // % ước tính (không có ADC)
  batt["charging"]       = false;
  batt["batteryVoltage"] = 0.0;
  batt["reach"]          = 0;
  // Backward-compat field cho Python (dễ parse hơn)
  pubDoc["battery_low"]      = battery_low;
  pubDoc["battery_blocking"] = battery_blocking;

  // ── Internal / backward-compat fields ────────────────────────────────────
  pubDoc["tag"]         = currentTag;    // Tương đương lastNodeId (int) — Python dùng
  pubDoc["prev_tag"]    = prevTag;       // Python dùng để tính heading
  pubDoc["status"]      = isAutoMode ? "auto" : "manual";  // Tương đương operatingMode
  pubDoc["action_info"] = (isAutoMode && currentMissionIndex < missionLength)
                          ? "running" : "idle";
  if (lastRecvCmdId != "") pubDoc["ack"]   = lastRecvCmdId;
  if (pendingEvent  != "") pubDoc["event"] = pendingEvent;

  // Gửi qua UART_ESP
  serializeJson(pubDoc, UART_ESP);
  UART_ESP.println();
  // Debug — in thẳng ra Serial, không dùng String để tránh heap fragmentation
  //Serial.print(F("Published: "));
  //serializeJson(pubDoc, Serial);
  // --- TO DO: XÓA ĐOẠN NÀY SAU (IN TỐC ĐỘ DEBUG) ---
  Serial.print(F(" | [DEBUG_SPEED] speed_ = ")); Serial.print(speed_);
  Serial.println();
}

void listenJson() {
  // Bộ tích lũy non-blocking: đọc từng byte sẵn có, chờ '\n' qua nhiều lần gọi.
  // Giải quyết IncompleteInput khi ESP32 gửi JSON lớn theo 2 chunk UART:
  //   chunk1 = 28 byte → lưu vào _ubuf, return (không parse)
  //   chunk2 = 321 byte → ghép vào _ubuf, tìm '\n' → parse JSON hoàn chỉnh
  // Không blocking → main loop (PID, motor control) không bị treo.
  static char          _ubuf[768];    // Buffer tĩnh xuyên lần gọi (plan max ~600 byte với lookahead=5)
  static int           _ulen  = 0;
  static unsigned long _ustart = 0;

  // Đọc tất cả byte sẵn có
  bool got_nl = false;
  while (UART_ESP.available() && _ulen < (int)sizeof(_ubuf) - 1) {
    char c = (char)UART_ESP.read();
    if (_ulen == 0 && c != '{') continue;  // Bỏ qua byte rác/whitespace trước JSON
    if (_ulen == 0) _ustart = millis();    // Ghi nhận thời điểm bắt đầu nhận gói
    if (c == '\n') { got_nl = true; break; }
    _ubuf[_ulen++] = c;
  }
  _ubuf[_ulen] = '\0';

  // Buffer overflow (> 1099 byte và vẫn chưa '\n') → dữ liệu hỏng, reset
  if (_ulen >= (int)sizeof(_ubuf) - 1 && !got_nl) {
    Serial.print(F("[UART ERR] Buffer overflow (len=")); Serial.print(_ulen); Serial.println(F("), reset."));
    _ulen = 0;
    return;
  }
  // Timeout: nhận được byte đầu rồi nhưng chưa có '\n' sau 2s → ESP32 bị treo, reset
  if (_ulen > 0 && !got_nl && (millis() - _ustart) > 2000UL) {
    Serial.print(F("[UART WARN] Timeout (len=")); Serial.print(_ulen); Serial.println(F("), reset."));
    _ulen = 0;
    return;
  }
  // Chưa nhận đủ gói → đợi lần gọi tiếp theo
  if (!got_nl) return;

  // ── Nhận đủ 1 gói: _ubuf chứa JSON, reset counter cho gói tiếp theo ──
  int rxLen = _ulen;
  _ulen = 0;

  Serial.print(F("[UART RX] len=")); Serial.print(rxLen);
  Serial.print(F(" data="));         Serial.println(_ubuf);
  if (rxLen == 0) return;

  DeserializationError error = deserializeJson(doc, _ubuf);

    if (error) {
      Serial.print(F("[UART ERR] deserializeJson failed: "));
      Serial.println(error.c_str());
      return;
    }

    // 1. Lấy ID của gói tin (để ACK lại cho App)
    if (doc.containsKey("id")) {
      lastRecvCmdId = doc["id"].as<String>();
    } else {
      lastRecvCmdId = "";
    }

    const char* cmd = doc["c"]; // Command code
    Serial.print(F("[CMD] c=")); Serial.println(cmd);

    if (strcmp(cmd, "plan") == 0) {
      // Từ chối plan khi đang trong chế độ chặn pin yếu
      // (battery_blocking = true chỉ khi: pin yếu + đã hoàn thành hành trình)
      // Nếu xe đang chạy dở thì vẫn nhận plan bình thường
      if (battery_blocking) {
        Serial.println(F("[PLAN REJECT] Pin yeu + da ve tram — cho Python xac nhan da sac du"));
        pendingEvent = "battery_need_charge";
        publishJson();
        return;
      }
      // Nhận kế hoạch mới
      JsonArray d = doc["d"];
      missionLength = 0;
      for (JsonObject v : d) {
        if (missionLength < 100) {
          missionPlan[missionLength].tag = v["t"];
          missionPlan[missionLength].action = v["a"];
          missionPlan[missionLength].value = v["v"];
          missionLength++;
        }
      }
      // Reset off-route counters khi nhận plan mới
      consecutiveUnknownTags = 0;
      missionSeenCount       = 0;
      // Cập nhật lịch sử rẽ khi nhận plan mới:
      // - GIỮ LẠI entries của thẻ HIỆN TẠI (tránh rẽ lại lần 2 khi server retry plan trong lúc đang rẽ)
      // - XÓA entries của các thẻ đã qua (missionIndex cũ không còn hợp lệ với plan mới)
      // Ví dụ: xe đang rẽ tại 107, plan retry đến → giữ history "đã rẽ tại 107"
      //        → khi STATE_RUNNING tái thực hiện bước TURN_L tại 107, stepAlreadyDone=true → bỏ qua
      {
        int _nc = 0;
        for (int _i = 0; _i < completedTurnsCount; _i++) {
          if (completedTurns[_i].tag == currentTag)
            completedTurns[_nc++] = completedTurns[_i];
        }
        completedTurnsCount = _nc;
      }
      lastTurnMissionIndex = -1;
      // --- Xử lý plan đến trễ: skip các bước của thẻ đã qua ---
      // Nếu plan có chứa currentTag → bắt đầu từ đó
      // Nếu không chứa → bắt đầu từ đầu (AGV chưa đến thẻ đầu)
      // Với các bước bị skip: vẫn áp dụng lệnh chiều (DIR_FWD/BWD) và tốc độ (SPEED)
      currentMissionIndex = 0;
      bool foundCurrentTag = false;
      // Khi currentTag=0 (vừa bật hoặc chưa đọc thẻ nào):
      // → Giả định AGV đang ở thẻ đầu tiên trong plan (người dùng đã đặt xe tại đó).
      // → Cho phép STATE_RUNNING thực hiện NGAY các lệnh tại thẻ xuất phát (kể cả TURN_L/R)
      //   mà không cần đợi RFID đọc lại thẻ đó.
      // → prevTag sẽ được set đúng khi xe di chuyển qua thẻ tiếp theo.
      if (currentTag == 0 && missionLength > 0) {
        currentTag = missionPlan[0].tag;
        Serial.print(F("[PLAN] currentTag=0 → gia dinh vi tri ban dau la the "));
        Serial.println(currentTag);
      }
      // Skip các bước của thẻ đã qua, áp dụng lệnh hướng/tốc độ của các bước bị bỏ qua
      if (currentTag > 0) {
        for (int si = 0; si < missionLength; si++) {
          if (missionPlan[si].tag == currentTag) {
            currentMissionIndex = si;  // Bắt đầu từ thẻ hiện tại
            foundCurrentTag = true;
            break;
          }
          // Bước bị skip: áp dụng setup (hướng, tốc độ) nhưng bỏ qua lệnh di chuyển
          // KHÔNG đổi chiều motor nếu đang quay — chieutien/chieului reset chân CW, phá vỡ quay
          int skippedAct = missionPlan[si].action;
          if (sysState != STATE_TURNING_L && sysState != STATE_TURNING_R) {
            if      (skippedAct == ACT_DIR_FWD)  chieutien();
            else if (skippedAct == ACT_DIR_BWD)  chieului();
          }
          if (skippedAct == ACT_SPEED) { 
            speed_ = constrain(missionPlan[si].value, speed_min, 255); 
            speedFromSystem = true; 
            speed_max = min((int)(speed_ + 30), 255);
          }
        }
      }
      // --- Xử lý plan nhận được khi đang quay hoặc vừa quay xong ---
      if (foundCurrentTag) {
        bool currentlyTurning = (sysState == STATE_TURNING_L || sysState == STATE_TURNING_R);
        if (currentlyTurning) {
          // Đang quay tại currentTag: tất cả bước tại thẻ này đã được thực hiện
          // (DIR đã đổi trước khi quay, TURN đang chạy) → nhảy sang thẻ tiếp theo.
          // deba() sẽ được gọi sau khi quay xong, bắt đầu từ thẻ kế tiếp.
          while (currentMissionIndex < missionLength &&
                 missionPlan[currentMissionIndex].tag == currentTag) {
            Serial.print(F("[PLAN-TURN] Bo qua buoc da thuc hien tai the "));
            Serial.print(currentTag); Serial.print(F(": act="));
            Serial.println(missionPlan[currentMissionIndex].action);
            currentMissionIndex++;
          }
        } else {
          // Không đang quay → dùng guard chống quay 2 lần (plan nhận sau khi quay xong <8s)
          bool recentTurnHere = (lastTurnTag == currentTag) &&
                                ((millis() - lastTurnTime) < 8000UL);
          while (recentTurnHere &&
                 currentMissionIndex < missionLength &&
                 missionPlan[currentMissionIndex].tag == currentTag &&
                 (missionPlan[currentMissionIndex].action == ACT_TURN_L ||
                  missionPlan[currentMissionIndex].action == ACT_TURN_R)) {
            Serial.print(F("[NO-DOUBLE-TURN] Bo qua re tai the "));
            Serial.println(currentTag);
            currentMissionIndex++;
          }
        }
      }
      // --- In chi tiết plan để debug ---
      if (foundCurrentTag) {
        Serial.print("[PLAN] Received! Bat dau tu the "); Serial.println(currentTag);
      } else {
        Serial.print("[PLAN] Received! currentTag="); Serial.print(currentTag);
        Serial.println(" (bat dau tu dau)");
      }
      Serial.print("[PLAN] Tong buoc: "); Serial.println(missionLength);
      for (int pi = currentMissionIndex; pi < missionLength; pi++) {
        Serial.print("  ["); Serial.print(pi); Serial.print("] The ");
        Serial.print(missionPlan[pi].tag); Serial.print(": ");
        switch (missionPlan[pi].action) {
          case ACT_WAIT_SYS:  Serial.print("WAIT_SYS");  break;
          case ACT_WAIT_USER: Serial.print("WAIT_USER"); break;
          case ACT_RUN:       Serial.print("CHAY");       break;
          case ACT_SPEED:     Serial.print("TOC_DO("); Serial.print(missionPlan[pi].value); Serial.print(")"); break;
          case ACT_TURN_R:    Serial.print("RE_PHAI");    break;
          case ACT_TURN_L:    Serial.print("RE_TRAI");    break;
          case ACT_DIR_FWD:   Serial.print("HUONG_TIEN"); break;
          case ACT_DIR_BWD:   Serial.print("HUONG_LUI");  break;
          case ACT_LIDAR_OFF: Serial.print("LIDAR_OFF");  break;
          case ACT_LIDAR_ON:  Serial.print("LIDAR_ON");   break;
          default:            Serial.print("ACT("); Serial.print(missionPlan[pi].action); Serial.print(")"); break;
        }
        Serial.println();
      }
      isAutoMode = true;
      // publishJson() không gọi trực tiếp ở đây — tránh UART_ESP TX block ngay sau khi
      // nhận packet lớn (ESP32 chưa sẵn sàng đọc UART ngược lại).
      // Heartbeat 1 giây trong loop() sẽ gửi ACK và trạng thái tự động.
      // Không gọi deba() nếu đang quay — để lần quay hiện tại hoàn thành trước.
      // Khi quay xong, code hoàn tất quay sẽ tự gọi deba() để tiếp tục plan mới.
      if (sysState != STATE_TURNING_L && sysState != STATE_TURNING_R) {
        deba();
      }
    }
    else if (strcmp(cmd, "run") == 0) {
      isAutoMode = true;
      // Cập nhật tốc độ nếu có truyền xuống qua biến "v" (value)
      int spd = doc["v"] | 0;
      if (spd > 0) { 
        speed_ = constrain(spd, speed_min, 255); 
        speedFromSystem = true; 
        speed_max = min((int)(speed_ + 30), 255);
      }
      // Cập nhật chiều nếu có truyền xuống qua biến "p" (param)
      const char* dir = doc["p"] | "";
      if (strlen(dir) > 0) {
        // Có hướng đi kèm -> Lệnh chạy thủ công override -> Xóa plan cũ để tránh xung đột
        missionLength = 0;
        currentMissionIndex = 0;
      }
      if (strcmp(dir, "fwd") == 0 || strcmp(dir, "toi") == 0) {
        chieutien();
        lidar_bank0();
      }
      else if (strcmp(dir, "bwd") == 0 || strcmp(dir, "lui") == 0) {
        chieului();
        lidar_bank1();
      }
      deba();
    }
    else if (strcmp(cmd, "stop") == 0) {
      isAutoMode  = false;
      debaManual  = false;           // Hủy deba thủ công nếu đang chạy
      sysState    = STATE_IDLE;      // Bắt buộc chuyển state — tránh updateAGV() bật lại motor
      dunglaigap();
      Serial.println(F("[STOP] Emergency stop — STATE_IDLE"));
    }
    else if (strcmp(cmd, "reset") == 0) {
      ResetBoard();
    }
    // Xử lý xác nhận từ App (App đã nhận được Event của AGV)
    // ── Python xác nhận đã sạc đủ (≥2h + tín hiệu pin khỏe) → mở khoá ─────────
    else if (strcmp(cmd, "battery_unlock") == 0) {
      battery_blocking = false;
      battery_low      = (digitalRead(PIN_PIN_YEU) == HIGH);  // Đọc lại thực tế
      guithongtinloi_hmi("");  // Xóa thông báo pin yếu trên HMI
      tatnhac();               // Tắt còi
      Serial.println(F("[BAT] battery_unlock: mo khoa nhan lenh — battery_blocking=false"));
      publishJson();           // Thông báo ngay trạng thái mới cho Python
    }
    else if (strcmp(cmd, "ack_event") == 0)
    {
      const char* ackedEvent = doc["d"]; // App gửi lại tên event đã nhận
      if (strcmp(pendingEvent.c_str(), ackedEvent ? ackedEvent : "") == 0) {
        Serial.print(F("App ACKED event: ")); Serial.println(pendingEvent);
        pendingEvent = ""; // Xóa sự kiện chờ, AGV chuyển sang trạng thái chờ lệnh mới
        // Không gọi publishJson() ở đây — tránh UART_ESP TX block khi nhận nhiều lệnh liên tiếp.
        // Heartbeat 1 giây trong loop() sẽ gửi trạng thái mới (không còn event).
      }
    }
    // ── Cập nhật pic nút tổ: {"c":"set_btn_pic","line":N,"pic":V} ──────────────
    // line: 1-60, pic: 28=chọn / 27=bỏ chọn
    // Dùng cho sự kiện hệ thống (server xóa nút tổ vừa giao, v.v.)
    else if (strcmp(cmd, "set_btn_pic") == 0)
    {
      int lineNum = doc["line"] | 0;
      int picVal  = doc["pic"]  | 27;
      if (lineNum >= 1 && lineNum <= 60) {
        char hcmd[24];
        snprintf(hcmd, sizeof(hcmd), "%s.pic=%d", buttonNames[lineNum - 1], picVal);
        hmiSendCommand(hcmd);
        BTstt[lineNum] = (picVal == 28) ? 1 : 0;
        Serial.print(F("[BTN-SYS] ")); Serial.print(buttonNames[lineNum - 1]);
        Serial.print(F(".pic=")); Serial.println(picVal);
      }
    }
    // ── Reset tất cả nút tổ về màu xám: {"c":"reset_team_btns"} ────────────────
    else if (strcmp(cmd, "reset_team_btns") == 0)
    {
      for (int _i = 0; _i < 60; _i++) {
        if (BTstt[_i + 1]) {
          char hcmd[24];
          snprintf(hcmd, sizeof(hcmd), "%s.pic=27", buttonNames[_i]);  // 27 = bỏ chọn
          hmiSendCommand(hcmd);
          delay(8);
          BTstt[_i + 1] = 0;
        }
      }
      supplyTeamCount = 0;
      Serial.println(F("[BTN] All team buttons reset (pic=27)."));
    }
    // ── Lệnh HMI trực tiếp: {"c":"hmi","cmd":"..."} ────────────────────────────
    else if (strcmp(cmd, "hmi") == 0)
    {
      const char* hmiCmd = doc["cmd"] | "";
      if (strlen(hmiCmd) > 0) {
        hmiSendCommand(hmiCmd);
        Serial.print(F("[HMI] ")); Serial.println(hmiCmd);
      }
    }
    // ── Lệnh DEBA thủ công: Chạy đến thẻ RFID kế tiếp rồi DỪNG ─────────────
    // Khác hoàn toàn với "run": không theo mission plan, dừng ngay sau 1 thẻ mới
    else if (strcmp(cmd, "deba") == 0)
    {
      // Guard: bỏ qua nếu đang quay — deba() sẽ phá vỡ turn mid-way
      if (sysState == STATE_TURNING_L || sysState == STATE_TURNING_R) {
        Serial.println(F("[DEBA] Bo qua: dang quay"));
        return;
      }
      missionLength       = 0;
      currentMissionIndex = 0;
      debaManual  = true;
      isAutoMode  = true;
      // "spd" (tùy chọn): set tốc độ nếu Python gửi kèm
      int spd = doc["spd"] | 0;
      if (spd > 0) { 
        speed_ = constrain(spd, speed_min, 255); 
        speedFromSystem = true; 
        speed_max = min((int)(speed_ + 30), 255);
      }
      // "dir" (tùy chọn): set chiều TRƯỚC khi chạy — atomic, không cần gửi 2 lệnh riêng
      // Nếu chiều đã đúng rồi, chieutien/chieului thoát ngay (không delay)
      // Nếu cần đổi chiều, có delay để bảo vệ hộp số — deba() sẽ mở phanh + chạy
      const char* dir = doc["dir"] | "";
      if      (strcmp(dir, "toi") == 0) chieutien();
      else if (strcmp(dir, "lui") == 0) chieului();
      // deba() tự gọi mothang() bên trong
      deba();
      Serial.print(F("[DEBA MANUAL] dir=")); Serial.print(dir[0] ? dir : "none");
      Serial.print(F(" spd=")); Serial.print(spd);
      Serial.println(F(" — Dang chay den the ke tiep..."));
    }
    // ── Lệnh ACTION tức thời: thực thi ngay 1 hành động, không cần đến thẻ ──
    // Dùng cho Điều khiển thủ công (quay, tốc độ, lidar, đèn, phanh, v.v.)
    // Payload: {"c":"action", "a":<action_code>, "v":<value>}
    else if (strcmp(cmd, "action") == 0)
    {
      int act = doc["a"] | 0;
      int val = doc["v"] | 0;
      executeSingleAction(act, val);
      publishJson();
    }
}

// ── executeSingleAction: Thực thi 1 hành động tức thời, không phụ thuộc vào thẻ ──
// Được gọi bởi lệnh {"c":"action","a":X,"v":Y} từ App điều khiển thủ công.
void executeSingleAction(int action, int val) {
  Serial.print("[MANUAL ACTION] a="); Serial.print(action);
  Serial.print(" v="); Serial.println(val);
  switch (action) {
    // ── Tốc độ ──────────────────────────────────────────────────────────
    case ACT_SPEED:
      speed_ = constrain(val, speed_min, 255);
      speedFromSystem = true;
      speed_max = min((int)(speed_ + 30), 255);
      Serial.print("[MANUAL] Speed set to "); Serial.println(speed_);
      break;
    // ── Chiều di chuyển ─────────────────────────────────────────────────
    case ACT_DIR_FWD:
      chieutien();
      lidar_bank0();
      break;
    case ACT_DIR_BWD:
      chieului();
      lidar_bank1();
      break;
    // ── Quay (chỉ thực hiện khi xe đứng yên) ───────────────────────────
    case ACT_TURN_L:
      dunglaigap();
      delay(100);
      mothang();
      // Bật cảm biến hướng hiện tại trước khi quay — cần cho ss8/ss9 detect line mới
      if (state == "toi") { digitalWrite(sstoi_0V, HIGH); digitalWrite(sstoi_24V, HIGH); }
      else                 { digitalWrite(sslui_0V, HIGH); digitalWrite(sslui_24V, HIGH); }
      chieuqueotrai_90();
      sysState    = STATE_TURNING_L;
      stateTimer  = millis();
      turnPhase1  = true; turnLineLost = false;
      analogWrite(PWM_T, 45);
      analogWrite(PWM_P, 45);
      break;
    case ACT_TURN_R:
      dunglaigap();
      delay(200);
      mothang();
      // Bật cảm biến hướng hiện tại trước khi quay — cần cho ss8/ss9 detect line mới
      if (state == "toi") { digitalWrite(sstoi_0V, HIGH); digitalWrite(sstoi_24V, HIGH); }
      else                 { digitalWrite(sslui_0V, HIGH); digitalWrite(sslui_24V, HIGH); }
      chieuqueophai_90();
      sysState    = STATE_TURNING_R;
      stateTimer  = millis();
      turnPhase1  = true; turnLineLost = false;
      analogWrite(PWM_T, 45);
      analogWrite(PWM_P, 45);
      break;
    // ── Lidar / Vật cản ─────────────────────────────────────────────────
    case ACT_LIDAR_OFF: lidar_bank1();        break;  // 20: Tắt vật cản
    case ACT_LIDAR_ON:  lidar_bank0();        break;  // 21: Bật vật cản
    // ── Âm thanh ────────────────────────────────────────────────────────
    case ACT_NHAC_START:    nhacstar();       break;  // 22
    case ACT_NHAC_STOP:     nhacstop();       break;  // 23
    case ACT_NHAC_XIN_LIEU: nhacxincaplieu(); break;  // 24
    case ACT_NHAC_MO_CUA:   nhacmocua();      break;  // 25
    case ACT_NHAC_XIN_RE:   nhacxinre();      break;  // 26
    case ACT_NHAC_TAT:      tatnhac();        break;  // 27
    // ── Phanh ───────────────────────────────────────────────────────────
    case ACT_BRAKE_ON:  dongthang(); break;  // 28
    case ACT_BRAKE_OFF: mothang();   break;  // 29
    // ── Móc hàng ────────────────────────────────────────────────────────
    case ACT_HOOK_RAISE: nang_moc(); break;  // 30
    case ACT_HOOK_LOWER: ha_moc();   break;  // 31
    // ── Đèn tháp ────────────────────────────────────────────────────────
    case ACT_DEN_VANG: batden_vang_3thap();  break;  // 32
    case ACT_DEN_XANH: batden_xanh_3thap();  break;  // 33
    case ACT_DEN_TAT:  tatden_3thap();       break;  // 34
    default:
      Serial.print("[MANUAL ACTION] Unknown action: "); Serial.println(action);
      break;
  }
}

// --- CÁC HÀM STUB ĐỂ FIX LỖI BUILD (DO LOGIC CŨ VẪN GỌI) ---
void publish(String topic, uint8_t id, String data, char ack) {
  // Hàm cũ: Tạm thời in ra Serial để debug, không gửi qua UART_ESP cũ nữa
  Serial.println("Legacy Publish: " + topic + " Data: " + data);
}

bool waitForAck(String topic, uint8_t id, String dataSent, char expectedAck) {
  // Hàm cũ: Luôn trả về true để không bị treo vòng lặp while
  return true;
}

void processMessage() {
  // Hàm cũ: Gọi listenJson để thay thế
  listenJson();
}

// --- HẾT PHẦN GIAO TIẾP MỚI ---

// Đo SRAM trống thực tế tại thời điểm gọi (AVR-specific)
int freeRam() {
  extern int __heap_start, *__brkval;
  int v;
  return (int)&v - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}

void setup()
{
  tatvatcan = 0;
  delay(2000);
  Serial.begin(115200);
  Serial.print(F("[MEM] Free SRAM after Serial.begin: ")); Serial.println(freeRam());
  Serial.print(F("[MEM] sizeof(doc)="));    Serial.print(sizeof(doc));
  Serial.print(F("  sizeof(pubDoc)="));    Serial.println(sizeof(StaticJsonDocument<1024>));
  Serial1.begin(9600);                    // GIAO TIEP JY-L8800 truoc
  Serial1.setTimeout(50);                 // Giới hạn blocking của readBytes: 50ms (mặc định 1000ms)
                                          // Tránh docrfid() treo PID 1 giây khi frame RFID không đủ byte
  Serial2.begin(9600);                    // GIAO TIEP HMI
  UART_ESP.begin(115200); // Serial3 hardware UART: TX3=pin14, RX3=pin15
  // Không cần setTimeout: listenJson() dùng bộ tích lũy non-blocking thay vì readStringUntil
  
  nexInit();                              //inicializa nextion
  delay(500);                             // This dalay is just in case the nextion display didn't start yet, to be sure it will receive the following command.
 // Attach callback chung cho buttons line
  for (int i = 0; i < 65; i++) 
  {
    if (buttons[i] != NULL) 
    {
      buttons[i]->attachPush(lineButtonPushCallback, buttons[i]);
    }
  }
  // Attach callback chung cho buttons chức năng
  b4.attachPush(b4PushCallback, &b4);
  b8.attachPush(b8PushCallback, &b8);
  b11.attachPush(b11PushCallback, &b11);
  b21.attachPush(b21PushCallback, &b21);
  b37.attachPush(b37PushCallback, &b37);
  page0.attachPush(page0PushCallback);  // Page press event
  page1.attachPush(page1PushCallback);
  dbSerialPrintln("setup done");
  pinMode(PWM_T, OUTPUT);
  pinMode(PWM_P, OUTPUT);
  pinMode(CW_T, OUTPUT);  // dao chieu dc trai
  pinMode(CW_P, OUTPUT);  //dap chieu dc phai
  pinMode(BREAK12, OUTPUT);
  pinMode(I_stop, OUTPUT);
  pinMode(I_start, OUTPUT);
  pinMode(I_1, OUTPUT);
  pinMode(lidar_X0, OUTPUT);
  pinMode(spare_X2, OUTPUT);  // RS wifi bằng việc set lên mức cao, bình thường là có điện.
  pinMode(denbao_RFID, OUTPUT);
  pinMode(dieukhien_denxanh, OUTPUT);
  pinMode(dieukhien_denvang, OUTPUT);
  pinMode(sstoi_0V, OUTPUT);
  pinMode(sstoi_24V, OUTPUT);
  pinMode(sslui_0V, OUTPUT);
  pinMode(sslui_24V, OUTPUT);
  pinMode(ss1, INPUT_PULLUP);
  pinMode(ss2, INPUT_PULLUP);
  pinMode(ss3, INPUT_PULLUP);
  pinMode(ss4, INPUT_PULLUP);
  pinMode(ss5, INPUT_PULLUP);
  pinMode(ss6, INPUT_PULLUP);
  pinMode(ss7, INPUT_PULLUP);
  pinMode(ss8, INPUT_PULLUP);
  pinMode(ss9, INPUT_PULLUP);
  pinMode(ss10, INPUT_PULLUP);
  pinMode(ss11, INPUT_PULLUP);
  pinMode(ss12, INPUT_PULLUP);
  pinMode(ss13, INPUT_PULLUP);
  pinMode(ss14, INPUT_PULLUP);
  pinMode(ss15, INPUT_PULLUP);
  pinMode(ss16, INPUT_PULLUP);
  pinMode(CBVC1, INPUT_PULLUP);
  pinMode(CBVC2, INPUT_PULLUP);
  pinMode(CBVC3, INPUT_PULLUP);
  pinMode(CBVC4, INPUT_PULLUP);
  pinMode(CBVC5, INPUT_PULLUP);
  pinMode(CB_VACHAM, INPUT_PULLUP);
#ifdef ENABLE_BATTERY_SENSOR
  pinMode(PIN_PIN_YEU, INPUT_PULLUP);
#endif
  //pinMode(do_dungluongpin, INPUT_PULLUP);
  pinMode(cambienphat, OUTPUT);
  pinMode(nutbam_tien, INPUT_PULLUP);
  pinMode(nutbam_lui, INPUT_PULLUP);
  digitalWrite(I_stop, LOW);
  digitalWrite(I_start, LOW);
  analogWrite(PWM_T, 0);
  analogWrite(PWM_P, 0);
  mothang();
  
  // Chế độ lidar hoạt động bình thường
  digitalWrite(lidar_X0, HIGH);
  digitalWrite(spare_X2, LOW);  // mặc định khởi động xe thì bật về mức thấp => bật ESP
  lidar_bank0();
  digitalWrite(denbao_RFID, LOW);
  tatden_3thap();
  //delay(2000);
  guitrangthai_hmi("ĐANG KHỞI ĐỘNG...");
  // Serial1.print("$S#") và docrfid() bị xóa khỏi setup():
  // Vòng lặp kiểm tra RFID đã comment-out → response "$S#" không có 'F' → docrfid() trigger
  // dunglai() → read_sensor_values() → dunglaimatline() → xe quay + lỗi "Xe bị lệch đường từ"
  // RFID sẽ được đọc bình thường trong loop() khi xe bắt đầu chạy.
  demthoat = 0;
  tatvatcan = 0;
  chieutien();
  delay(2000);
  // laygiatrichuyen_hmi();  // tạm comment: mỗi getValue() timeout 100ms × 36 = 3.6s blocking
  laygiatri_hmi();        // Đọc tốc độ + thông số cơ bản từ HMI
  guitrangthai_hmi("ẤN NÚT <VỀ TRẠM>");
  guithongtinloi_hmi(" ");
  batden_vang_3thap();

  // ── Handshake UART: kiểm tra kết nối với ESP32 ──────────────────────────
  // Gửi ping → chờ tối đa 5s → in kết quả
  delay(500);  // Cho ESP32 boot xong trước
  Serial.println(F("[UART] Gui ping ESP32..."));
  UART_ESP.println(F("{\"c\":\"ping\"}"));
  {
    unsigned long t0   = millis();
    String        rbuf = "";
    bool          ok   = false;
    while (!ok && millis() - t0 < 5000UL) {
      while (UART_ESP.available()) {
        char c = (char)UART_ESP.read();
        if (c == '\n') {
          rbuf.trim();
          if (rbuf.indexOf("pong") >= 0) ok = true;
          rbuf = "";
        } else if (c != '\r') {
          rbuf += c;
        }
      }
    }
    if (ok) {
      Serial.println(F("[UART] ESP32 PONG OK  — UART hoat dong binh thuong!"));
    } else {
      Serial.println(F("[UART] ESP32 PONG TIMEOUT — Kiem tra day noi GPIO5->pin15 va GND chung!"));
    }
  }
  // ────────────────────────────────────────────────────────────────────────
}
void Bat_cambienphat() {
  digitalWrite(cambienphat, HIGH);
}
void Tat_cambienphat() {
  digitalWrite(cambienphat, LOW);
}
void lidar_bank0()
{
  // Chế độ hoạt động bình thường (ORG)
  //digitalWrite(lidar_X0, HIGH);
  // Hàm thay thế
  tatvatcan = 0;
}
void lidar_bank1() { //Lidar 20cm
  // Chế độ hoạt động lidar bank ngắn (ORG)
  //digitalWrite(lidar_X0, LOW);
  // Hàm thay thế
  tatvatcan = 1;
}

// --- Móc hàng — Stub (chờ code phần cứng) ---
void nang_moc() {
  // TODO: Thêm code điều khiển cơ cấu nâng móc hàng vào đây
  // Ví dụ: digitalWrite(PIN_HOOK_UP, HIGH); delay(1000); digitalWrite(PIN_HOOK_UP, LOW);
}
void ha_moc() {
  // TODO: Thêm code điều khiển cơ cấu hạ móc hàng vào đây
  // Ví dụ: digitalWrite(PIN_HOOK_DOWN, HIGH); delay(1000); digitalWrite(PIN_HOOK_DOWN, LOW);
}
void read_sensor_values()  // DO 4-5 LED
{
  bool sensorStates[17];
  sensorStates[1] = digitalRead(ss1);
  sensorStates[2] = digitalRead(ss2);
  sensorStates[3] = digitalRead(ss3);
  sensorStates[4] = digitalRead(ss4);
  sensorStates[5] = digitalRead(ss5);
  sensorStates[6] = digitalRead(ss6);
  sensorStates[7] = digitalRead(ss7);
  sensorStates[8] = digitalRead(ss8);
  sensorStates[9] = digitalRead(ss9);
  sensorStates[10] = digitalRead(ss10);
  sensorStates[11] = digitalRead(ss11);
  sensorStates[12] = digitalRead(ss12);
  sensorStates[13] = digitalRead(ss13);
  sensorStates[14] = digitalRead(ss14);
  sensorStates[15] = digitalRead(ss15);
  sensorStates[16] = digitalRead(ss16);
  // Normal_mode = 1 khi chạy bên ngoài, = 0 khi vào gần thang máy
  if (Normal_mode == 1) {
    //chuong trinh chay thang////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0;
    // chuong trinh lech trai////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.18;  // ORG 0.16
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 1.2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 1.2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 3;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 3.5;
    else if (sensorStates[1] == 0 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 5;

    // chuong trinh lech phai/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.18;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 1)
      error = -1.2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 1)
      error = -1.2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -3.5;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 0)
      error = -5;
  }
  if (Normal_mode == 0)  //chạy ngoài trời
  {
    //chuong trinh chay thang////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0;
    // chuong trinh lech trai////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.16;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0.9;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 1.2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 0 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 1.2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 0 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 0 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 2;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 0 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 3;
    else if (sensorStates[1] == 0 && sensorStates[2] == 0 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 3.5;
    else if (sensorStates[1] == 0 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 5;

    // chuong trinh lech phai/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 0 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = 0;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.16;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 0 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 0 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 1 && sensorStates[16] == 1)
      error = -0.6;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 0 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 1)
      error = -0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 0 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 1)
      error = -0.9;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 0 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -1.2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -1.2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 0 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 0 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -2;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 0 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -3;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 0 && sensorStates[16] == 0)
      error = -3.5;
    else if (sensorStates[1] == 1 && sensorStates[2] == 1 && sensorStates[3] == 1 && sensorStates[4] == 1 && sensorStates[5] == 1 && sensorStates[6] == 1 && sensorStates[7] == 1 && sensorStates[8] == 1 && sensorStates[9] == 1 && sensorStates[10] == 1 && sensorStates[11] == 1 && sensorStates[12] == 1 && sensorStates[13] == 1 && sensorStates[14] == 1 && sensorStates[15] == 1 && sensorStates[16] == 0)
      error = -5;
  }
  // Chạy không line từ 100ms
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1))) {
    conditionMetTime = millis();  // Ghi lại thời điểm điều kiện được thỏa mãn
    while (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1))) {
      if ((millis() - conditionMetTime >= 80)) {
        dunglaimatline();
        conditionMetTime = millis();  // Thiết lập lại thời gian
      }
      delay(5);  //chống CPU tràn
    }
  }
}
void read_sensor_values_trai_phai()  // DO 4-5 LED
{
  //chuong trinh chay thang////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 0;
  // chuong trinh lech trai////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 0;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 0.3;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 0.3;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 1.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 1.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 1.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 3;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 3.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 0) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 0) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 4;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 0) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 4.5;
  else if (((digitalRead(ss1) == 0) && (digitalRead(ss2) == 0) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 0) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 5;
  else if (((digitalRead(ss1) == 0) && (digitalRead(ss2) == 0) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 0) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 5.5;
  else if (((digitalRead(ss1) == 0) && (digitalRead(ss2) == 0) && (digitalRead(ss3) == 0) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 6;
  else if (((digitalRead(ss1) == 0) && (digitalRead(ss2) == 0) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 6.5;
  else if (((digitalRead(ss1) == 0) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 6.9;

  // chuong trinh lech phai/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 0) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = 0;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -0.3;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 0) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -0.8;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -1.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 0) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -1.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -1.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 0) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -3;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1)))
    error = -3.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 0) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 0) && (digitalRead(ss16) == 1)))
    error = -4;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 0) && (digitalRead(ss16) == 1)))
    error = -4.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 0) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 0) && (digitalRead(ss16) == 0)))
    error = -5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 0) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 0) && (digitalRead(ss16) == 0)))
    error = -5.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 0) && (digitalRead(ss15) == 0) && (digitalRead(ss16) == 0)))
    error = -6;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 0) && (digitalRead(ss16) == 0)))
    error = -6.5;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 0)))
    error = -6.9;
  else if (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1))) {
    error = error;
  } else
    error = error;
}
// Binh khai bao them:
unsigned long previousTime = 0;
double MaxI = 0.0005;

void resetPID() {
  error = 0; P = 0; I = 0; D = 0; PID_value = 0;
  previous_error = 0; previous_I = 0;
  filtered_error = 0.0;
  previous_PID_value = 0.0;
  pid_previousTime = millis();
}

void calculate_pid() 
{
  unsigned long now = millis();
  double deltaTime = (double)(now - pid_previousTime) / 1000.0;
  pid_previousTime = now;

  // Giới hạn deltaTime hợp lý cho AGV (10ms - 500ms)
  if (deltaTime < 0.01) 
  {
    deltaTime = 0.01;
  }
  else if (deltaTime > 0.5) 
  {
    deltaTime = 0.5;
  }

  // Lọc nhiễu cho error
  const double alpha = 0.65;  // Hệ số làm mượt (0-1), điều chỉnh để giảm nhiễu
  filtered_error = alpha * filtered_error + (1.0 - alpha) * error;

  // Tính P dựa trên error đã lọc
  P = filtered_error;

  // Tính và giới hạn I với anti-windup
  double MaxI = 50.0;  // Giới hạn tích phân, điều chỉnh theo hệ thống
  double potentialI = I + (filtered_error * deltaTime);
  if (potentialI > MaxI) 
  {
    I = MaxI;
  }
  else if (potentialI < -MaxI) 
  {
    I = -MaxI;
  } 
  else 
  {
    I = potentialI;
  }
  // Tính D với giới hạn để giảm nhiễu
  double deltaError = filtered_error - previous_error;
  D = deltaError / deltaTime;
  double maxD = 5.0;  // Giới hạn D, điều chỉnh nếu cần
  if (D > maxD) 
  {
    D = maxD;
  }
  else if (D < -maxD) 
  {
    D = -maxD;
  }

  // Điều chỉnh hệ số PID động theo mức độ lỗi (tùy chọn)
  double dynamic_Kp = Kp;
  double dynamic_Kd = Kd;
  if (abs(filtered_error) > 3.5) {  // Khi lỗi lớn, tăng Kp và giảm Kd
    dynamic_Kp = Kp * 1.2;          // Tăng phản hồi tỉ lệ
    dynamic_Kd = Kd * 0.8;          // Giảm vi phân để tránh lắc
  }

  // Tính PID tạm thời
  double new_PID_value = (dynamic_Kp * P) + (Ki * I) + (dynamic_Kd * D);

  // Giới hạn tốc độ thay đổi PID để giảm rung lắc
  double maxPIDChange = 15.0;  // Điều chỉnh nếu cần
  if (new_PID_value - previous_PID_value > maxPIDChange) {
    PID_value = previous_PID_value + maxPIDChange;
  } else if (new_PID_value - previous_PID_value < -maxPIDChange) {
    PID_value = previous_PID_value - maxPIDChange;
  } else {
    PID_value = new_PID_value;
  }

  // Giới hạn đầu ra động theo mức độ lỗi
  double outputMax = abs(filtered_error) * 30.0 + 15.0;
  double outputMin = abs(filtered_error) * -30.0 - 15.0;

  // Thêm giới hạn cứng để tránh vượt quá khả năng động cơ
  const double absoluteMax = 100.0;  // Giới hạn tối đa của động cơ, điều chỉnh theo thực tế
  if (outputMax > absoluteMax) outputMax = absoluteMax;
  if (outputMin < -absoluteMax) outputMin = -absoluteMax;


  // Áp dụng giới hạn và chống windup
  if (PID_value > outputMax) {
    PID_value = outputMax;
    I -= filtered_error * deltaTime;  // Giảm tích phân khi bão hòa
  } else if (PID_value < outputMin) {
    PID_value = outputMin;
    I -= filtered_error * deltaTime;  // Giảm tích phân khi bão hòa
  }

  // Reset PID khi error nhỏ (deadband)
  const double deadband = 0.2;  // Ngưỡng deadband, điều chỉnh nếu cần
  if (abs(filtered_error) < deadband) {
    PID_value = 0;
    I = 0;  // Reset tích phân để tránh tích lũy không cần thiết
  }
  // Lưu giá trị cho lần sau
  previous_error = filtered_error;
  previous_PID_value = PID_value;
}
void motor_control() 
{
  if (state == "toi") {
    left_motor_speed = initial_motor_speed + PID_value;
    right_motor_speed = initial_motor_speed - PID_value;
  } else if (state == "lui") {
    left_motor_speed = initial_motor_speed - PID_value;
    right_motor_speed = initial_motor_speed + PID_value;
  }
  if (left_motor_speed > speed_max) {
    left_motor_speed = speed_max;
  } else if (left_motor_speed < speed_min) {
    left_motor_speed = speed_min;
  } else left_motor_speed = left_motor_speed;
  ////////////////////////////////////////////////////
  if (right_motor_speed > speed_max) {
    right_motor_speed = speed_max;
  } else if (right_motor_speed < speed_min) {
    right_motor_speed = speed_min;
  } else right_motor_speed = right_motor_speed;
  /////////////////////////////////////////////////////
  {
    analogWrite(PWM_T, left_motor_speed);
    analogWrite(PWM_P, right_motor_speed);
  }
//   Serial.print("error: ");
//   Serial.print(error);
//   Serial.print("  ");
//   Serial.print("PID_value: ");
//   Serial.print(PID_value);
//   Serial.print("  ");
//   Serial.print(left_motor_speed);
//   Serial.print("  ");
//   Serial.println(right_motor_speed);

}

// --- HÀM KIỂM TRA VẬT CẢN (KHÔNG BLOCKING) ---
bool checkObstacle() {
  bool obstacle = false;
  if (state == "toi") {
    if (batLidardai == 1) {
       if (digitalRead(CBVC1) == 1 || digitalRead(CBVC2) == 1 || digitalRead(CBVC5) == 1) obstacle = true;
    } else {
       if (digitalRead(CBVC1) == 1 || digitalRead(CBVC2) == 1) obstacle = true;
    }
  } else { // lui
     if (digitalRead(CBVC3) == 1 || digitalRead(CBVC4) == 1) obstacle = true;
  }
  return obstacle;
}

// --- HÀM CẬP NHẬT TRẠNG THÁI AGV (GỌI LIÊN TỤC TRONG LOOP) ---
void updateAGV() 
{
  switch (sysState) 
  {
    case STATE_IDLE:
    case STATE_WAIT_USER:
      // Xe đứng yên, chờ người dùng bấm b11 tại tổ giao hàng
      analogWrite(PWM_T, 0);
      analogWrite(PWM_P, 0);
      // Nhấp nháy b11 mỗi 300ms khi đang chờ tại tổ giao hàng
      if (deliveryWaiting && (millis() - b11BlinkTimer >= 300)) {
        b11BlinkTimer = millis();
        b11BlinkState = !b11BlinkState;
        hmiSendCommand(b11BlinkState ? "b11.pic=38" : "b11.pic=37");
      }
      break;
    case STATE_WAIT_SYS:
      // Xe đứng yên, chờ lệnh từ hệ thống
      analogWrite(PWM_T, 0);
      analogWrite(PWM_P, 0);
      // Nhấp nháy b37 mỗi 300ms khi đang chờ cấp liệu
      if (waitingForSupply && (millis() - b37BlinkTimer >= 300)) {
        b37BlinkTimer = millis();
        b37BlinkState = !b37BlinkState;
        hmiSendCommand(b37BlinkState ? "b37.pic=30" : "b37.pic=29");
      }
      break;
    case STATE_RUNNING:
      // 1. Kiểm tra vật cản
      if (checkObstacle()) 
      {
        sysState = STATE_OBSTACLE;
        dunglaigap();
        guithongtinloi_hmi("Có vật cản");
        nhacstop();
        triggerEvent("obstacle"); // Báo cho server biết có vật cản
        return;
      }

      // 2. Kiểm tra Nhiệm vụ (RFID)
      docrfid();
      // QUAN TRỌNG: docrfid() có thể gọi onNewTagDetected() → đổi sysState (IDLE/OBSTACLE...)
      // Phải kiểm tra lại — nếu không còn STATE_RUNNING thì thoát ngay, không chạy PID
      if (sysState != STATE_RUNNING) break;

      if (isAutoMode && currentMissionIndex < missionLength)
      {
         // --- Runtime forward-scan: nếu RFID bỏ sót thẻ giữa chừng ---
         // Khi currentTag không khớp bước hiện tại, quét về phía trước để tìm bước có tag đó.
         // Áp dụng DIR/SPEED của các bước bị skip (như logic late-arrival khi nhận plan).
         if (currentTag != 0 && currentTag != missionPlan[currentMissionIndex].tag) 
         {
           for (int fi = currentMissionIndex + 1; fi < missionLength; fi++) {
             if (missionPlan[fi].tag == currentTag) {
               Serial.print("[SKIP] RFID bo sot tag, nhay tu buoc ");
               Serial.print(currentMissionIndex);
               Serial.print(" -> ");
               Serial.println(fi);
               // Áp dụng setup từ các bước bị bỏ qua
               for (int si = currentMissionIndex; si < fi; si++) {
                 int skAct = missionPlan[si].action;
                 if      (skAct == ACT_DIR_FWD) chieutien();
                 else if (skAct == ACT_DIR_BWD) chieului();
                 else if (skAct == ACT_SPEED)   { speed_ = missionPlan[si].value; speedFromSystem = true; }
               }
               currentMissionIndex = fi;
               break;
             }
           }
         }

         // Biến currentTag giờ được cập nhật trong docrfid() và onNewTagDetected()
         if (currentTag == missionPlan[currentMissionIndex].tag)
         {
            // Thực thi hành động tại thẻ
            int action = missionPlan[currentMissionIndex].action;
            int val = missionPlan[currentMissionIndex].value;
            if (action == ACT_WAIT_CHARGE)
            {
               // Về trạm sạc: đèn vàng + bật cảm biến phát, KHÔNG loa/nhấp nháy
               sysState = STATE_WAIT_SYS;
               dunglaigap();
               isAutoMode = false;
               batden_vang_3thap();             // Đèn vàng: xe đang chờ tại trạm sạc
               Bat_cambienphat();               // Bật cảm biến phát để sạc

               // ── Reset trạng thái về mặc định (như lúc mới khởi động) ──────────
               // Mục đích: lần điều tiếp theo xe đi tiến + lidar bình thường + phanh sẵn sàng
               chieutien();      // Đặt chiều TIẾN (reset sau khi lùi về trạm)
               lidar_bank0();    // Cảm biến vật cản bình thường (bank0)
               speedFromSystem = false;  // Không còn override tốc độ
               completedTurnsCount  = 0;  // Xóa lịch sử rẽ để nhiệm vụ tiếp theo không bị bỏ qua
               lastTurnMissionIndex = -1;
               missionLength = 0;        // Xóa plan cũ — nhiệm vụ tiếp theo sẽ nhận plan mới
               currentMissionIndex = 0;
               waitingForSupply = false; // Reset cờ chờ cấp hàng
               deliveryWaiting  = false; // Reset cờ chờ giao hàng
               hmiSendCommand("b8.pic=39"); // Nút về trạm về trạng thái bình thường
               guitrangthai_hmi("SAN SANG"); // Hiển thị sẵn sàng nhận nhiệm vụ tiếp theo

               triggerEvent("arrived_wait_sys");
               publishJson();
               return;
            }
            else if (action == ACT_WAIT_SYS || action == ACT_WAIT_USER)
            {
               sysState = (action == ACT_WAIT_SYS) ? STATE_WAIT_SYS : STATE_WAIT_USER;
               dunglaigap();
               isAutoMode = false; // Tạm dừng auto để chờ lệnh/xác nhận
               // Gửi sự kiện lên server báo đã đến điểm chờ
               if (action == ACT_WAIT_SYS) {
                 nhacxincaplieu();              // Bật loa yêu cầu cấp liệu
                 waitingForSupply = true;       // Bắt đầu nhấp nháy b37
                 b37BlinkTimer = millis();
                 b37BlinkState = false;
                 hmiSendCommand("b37.pic=29"); // Đặt về màu xám ban đầu
                 triggerEvent("arrived_wait_sys");
               } else {
                 // Tại tổ giao hàng: bật nhạc đến tổ + nhấp nháy b11, chờ người dùng bấm b11
                 nhacdenline();                 // Nhạc báo đến tổ giao hàng (khác nhacxincaplieu)
                 deliveryWaiting = true;        // Bắt đầu nhấp nháy b11
                 b11BlinkTimer = millis();
                 b11BlinkState = false;
                 hmiSendCommand("b11.pic=37"); // Đặt về màu xám ban đầu
                 triggerEvent("arrived_wait_user");
               }
               publishJson();
               return;
            }
            else if (action == ACT_TURN_L)
            {
               // Chống quay 2 lần: dùng missionIndex để phân biệt từng bước trong cùng plan
               // → 2 TURN_L liên tiếp cùng tag sẽ có missionIndex khác nhau → không bị chặn
               bool stepAlreadyDone = false;
               for (int ci = 0; ci < completedTurnsCount; ci++) {
                 if (completedTurns[ci].missionIndex == currentMissionIndex) {
                   stepAlreadyDone = true;
                   break;
                 }
               }
               // recentTurnHere: chặn RETRY khi completedTurns đã bị xóa (plan mới/duplicate)
               // Chỉ kích hoạt khi completedTurnsCount==0 (backup) — tránh chặn lần quay thứ 2
               // hợp lệ tại cùng thẻ (vd: 2×TURN_L), vì lần đầu đã ghi vào completedTurns (count>0)
               bool recentTurnHere = (completedTurnsCount == 0)
                                  && (lastTurnTag == currentTag)
                                  && (millis() - lastTurnTime < 8000UL)
                                  && (lastTurnApproachTag == prevTag);
               if (stepAlreadyDone || recentTurnHere) {
                 Serial.print(F("[STEP-DONE] Bo qua RE_TRAI tai the "));
                 Serial.println(currentTag);
                 currentMissionIndex++;
                 // Không return — tiếp tục motor_control() để xe chạy thẳng
               } else {
                 // Ghi nhận bước đã thực hiện vào completedTurns[]
                 if (completedTurnsCount < MAX_COMPLETED_TURNS) {
                   completedTurns[completedTurnsCount].missionIndex = currentMissionIndex;
                   completedTurns[completedTurnsCount].tag          = currentTag;
                   completedTurns[completedTurnsCount].action       = ACT_TURN_L;
                   completedTurns[completedTurnsCount].approachTag  = prevTag;
                   completedTurnsCount++;
                 }
                 lastTurnTag          = currentTag;
                 lastTurnMissionIndex = currentMissionIndex;
                 lastTurnApproachTag  = prevTag;
                 lastTurnTime         = millis();
                 dunglaigap();    // Dừng + phanh — xe vào đúng vị trí vuông vắn
                 delay(100);      // Chờ thêm để xe ổn định hoàn pu
                 mothang();       // Mở phanh, cho phép động cơ quay
                 chieuqueotrai_90();
                 sysState = STATE_TURNING_L;
                 stateTimer = millis();
                 turnPhase1 = true; turnLineLost = false;
                 analogWrite(PWM_T, 45);
                 analogWrite(PWM_P, 45);
                 currentMissionIndex++;
                 return;
               }
            }
            else if (action == ACT_TURN_R)
            {
               // Chống quay 2 lần: dùng missionIndex để phân biệt từng bước trong cùng plan
               bool stepAlreadyDone = false;
               for (int ci = 0; ci < completedTurnsCount; ci++) {
                 if (completedTurns[ci].missionIndex == currentMissionIndex) {
                   stepAlreadyDone = true;
                   break;
                 }
               }
               // recentTurnHere: chặn RETRY khi completedTurns đã bị xóa (plan mới/duplicate)
               // Chỉ kích hoạt khi completedTurnsCount==0 (backup) — tránh chặn lần quay thứ 2 hợp lệ
               bool recentTurnHere = (completedTurnsCount == 0)
                                  && (lastTurnTag == currentTag)
                                  && (millis() - lastTurnTime < 8000UL)
                                  && (lastTurnApproachTag == prevTag);
               if (stepAlreadyDone || recentTurnHere) {
                 Serial.print(F("[STEP-DONE] Bo qua RE_PHAI tai the "));
                 Serial.println(currentTag);
                 currentMissionIndex++;
                 // Không return — tiếp tục motor_control() để xe chạy thẳng
               } else {
                 // Ghi nhận bước đã thực hiện vào completedTurns[]
                 if (completedTurnsCount < MAX_COMPLETED_TURNS) {
                   completedTurns[completedTurnsCount].missionIndex = currentMissionIndex;
                   completedTurns[completedTurnsCount].tag          = currentTag;
                   completedTurns[completedTurnsCount].action       = ACT_TURN_R;
                   completedTurns[completedTurnsCount].approachTag  = prevTag;
                   completedTurnsCount++;
                 }
                 lastTurnTag          = currentTag;
                 lastTurnMissionIndex = currentMissionIndex;
                 lastTurnApproachTag  = prevTag;
                 lastTurnTime         = millis();
                 dunglaigap();    // Dừng + phanh — xe vào đúng vị trí vuông vắn
                 delay(200);      // Chờ thêm để xe ổn định hoàn toàn
                 mothang();       // Mở phanh, cho phép động cơ quay
                 chieuqueophai_90();
                 sysState = STATE_TURNING_R;
                 stateTimer = millis();
                 turnPhase1 = true; turnLineLost = false;
                 analogWrite(PWM_T, 45);
                 analogWrite(PWM_P, 45);
                 currentMissionIndex++;
                 return;
               } // end else (execute turn)
            }
            else if (action == ACT_SPEED)
             {
               speed_ = constrain(val, speed_min, 255); // Cập nhật tốc độ đích
               speedFromSystem = true; // Python đã gửi tốc độ → không dùng tốc độ HMI nữa
               speed_max = min((int)(speed_ + 30), 255);
               currentMissionIndex++;
            } 
            else if (action == ACT_DIR_FWD)
            { // 7: Đặt chiều tiến (chieutien() tự kiểm tra và dừng nếu cần)
               chieutien();
               lidar_bank0(); // Bật lại vật cản khi đi tiến
               initial_motor_speed = 0; // Reset tốc độ — chờ ACT_RUN/deba() mới chạy tiếp
               currentMissionIndex++;
               return; // Thoát ngay — không cho motor_control() ghi đè PWM
            }
            else if (action == ACT_DIR_BWD)
            { // 8: Đặt chiều lùi (chieului() tự kiểm tra và dừng nếu cần)
               chieului();
               lidar_bank1(); // Tắt vật cản khi đi lùi
               initial_motor_speed = 0; // Reset tốc độ — chờ ACT_RUN/deba() mới chạy tiếp
               currentMissionIndex++;
               return; // Thoát ngay — không cho motor_control() ghi đè PWM
            } 
            else if (action == ACT_LIDAR_OFF) 
            { // 20: Tắt vật cản (trước khi quay/lùi)
               lidar_bank1();
               currentMissionIndex++;
            } else if (action == ACT_LIDAR_ON)
            { // 21: Bật vật cản (bank0)
               lidar_bank0();
               currentMissionIndex++;
            }
            // --- Nhạc / Âm thanh ---
            else if (action == ACT_NHAC_START)    { nhacstar();       currentMissionIndex++; } // 22
            else if (action == ACT_NHAC_STOP)     { nhacstop();       currentMissionIndex++; } // 23
            else if (action == ACT_NHAC_XIN_LIEU) { nhacxincaplieu(); currentMissionIndex++; } // 24
            else if (action == ACT_NHAC_MO_CUA)   { nhacmocua();      currentMissionIndex++; } // 25
            else if (action == ACT_NHAC_XIN_RE)   { nhacxinre();      currentMissionIndex++; } // 26
            else if (action == ACT_NHAC_TAT)      { tatnhac();        currentMissionIndex++; } // 27
            // --- Phanh ---
            else if (action == ACT_BRAKE_ON)      { dongthang();      currentMissionIndex++; } // 28: Đóng phanh
            else if (action == ACT_BRAKE_OFF)     { mothang();        currentMissionIndex++; } // 29: Mở phanh
            // --- Móc hàng (stub) ---
            else if (action == ACT_HOOK_RAISE)    { nang_moc();       currentMissionIndex++; } // 30: Nâng móc
            else if (action == ACT_HOOK_LOWER)    { ha_moc();         currentMissionIndex++; } // 31: Hạ móc
            // --- Đèn tháp ---
            else if (action == ACT_DEN_VANG)      { batden_vang_3thap();  currentMissionIndex++; } // 32
            else if (action == ACT_DEN_XANH)      { batden_xanh_3thap();  currentMissionIndex++; } // 33
            else if (action == ACT_DEN_TAT)       { tatden_3thap();        currentMissionIndex++; } // 34
            // --- Quay khi lùi (9, 10) — xử lý giống quay bình thường ---
            else if (action == ACT_TURN_L_BWD)
            { // 9: Quay trái (dùng cho quay 180 trên đường thẳng)
               lastTurnTag  = currentTag;
               lastTurnTime = millis();
               dunglaigap();
               delay(100);
               mothang();
               chieuqueotrai_90();
               sysState = STATE_TURNING_L;
               stateTimer = millis();
               turnPhase1 = true; turnLineLost = false;
               analogWrite(PWM_T, 45);
               analogWrite(PWM_P, 45);
               currentMissionIndex++;
               return;
            }
            else if (action == ACT_TURN_R_BWD)
            { // 10: Quay phải (dùng cho quay 180 trên đường thẳng)
               lastTurnTag  = currentTag;
               lastTurnTime = millis();
               dunglaigap();
               delay(100);
               mothang();
               chieuqueophai_90();
               sysState = STATE_TURNING_R;
               stateTimer = millis();
               turnPhase1 = true; turnLineLost = false;
               analogWrite(PWM_T, 45);
               analogWrite(PWM_P, 45);
               currentMissionIndex++;
               return;
            }
            else if (action == ACT_RUN)
            { // 3: Bắt đầu chạy — mở phanh + bật RFID + soft start
               deba();
               currentMissionIndex++;
            }
            else
            { // Các action không xác định khác
               currentMissionIndex++;
            }
         }
      }

      // 3. Điều khiển chạy dò line
      // KHÔNG gọi mothang() ở đây — phanh được mở 1 lần bởi deba() khi bắt đầu chạy
      // Gọi mothang() mỗi vòng loop sẽ override lệnh dunglaigap() từ onNewTagDetected()
      // → xe không dừng được (phanh bị mở ngay sau khi đóng)
      read_sensor_values();
      calculate_pid();
      
      // Soft Start / Soft Stop: Tăng/Giảm tốc từ từ mỗi vòng lặp — không giật
      if (initial_motor_speed < speed_) {
        initial_motor_speed += 5;          // Tăng tốc độ nhanh hơn
        if (initial_motor_speed > speed_) initial_motor_speed = speed_;
      } else if (initial_motor_speed > speed_) {
        initial_motor_speed -= 5;          // Giảm mượt (không nhảy xuống tức thì)
        if (initial_motor_speed < speed_) initial_motor_speed = speed_;
      }
      
      motor_control();
      break;

    case STATE_OBSTACLE:
      if (!checkObstacle()) {
        // Vật cản vừa biến mất — bắt đầu đếm thời gian chờ 3 giây
        if (conditionMetTime == 0) {
          conditionMetTime = millis();
          guithongtinloi_hmi("Chờ 3s...");
        } else if (millis() - conditionMetTime >= 3000) {
          // Đã chờ đủ 3 giây → tiếp tục chạy
          conditionMetTime = 0;
          guithongtinloi_hmi("");
          triggerEvent("obstacle_cleared");
          tatnhac();
          deba(); // Gọi deba() để bật đèn xanh + soft start + chuyển STATE_RUNNING
        }
      } else {
        // Vật cản vẫn còn → reset timer (tránh timer chạy khi cản chợt biến rồi lại xuất hiện)
        conditionMetTime = 0;
        guithongtinloi_hmi("Có vật cản");
      }
      break;

    case STATE_TURNING_L:
    {
      if (digitalRead(CB_VACHAM) == 0) { dunglaigap(); sysState = STATE_OBSTACLE; return; }
      
      bool oldEdgeHit = false, newEdgeHit = false, centerHit = false;
      if (state == "toi") {
        oldEdgeHit = (digitalRead(ss15) == 0 || digitalRead(ss16) == 0); // Vạch cũ chạm mép phải
        newEdgeHit = (digitalRead(ss1) == 0 || digitalRead(ss2) == 0);   // Vạch mới chạm mép trái
        centerHit  = (digitalRead(ss6) == 0 || digitalRead(ss7) == 0 || digitalRead(ss8) == 0 || digitalRead(ss9) == 0);
      } else { // Khi đi lùi, đuôi xe quét ngược lại nên các mắt cảm biến đảo ngược
        oldEdgeHit = (digitalRead(ss1) == 0 || digitalRead(ss2) == 0);
        newEdgeHit = (digitalRead(ss15) == 0 || digitalRead(ss16) == 0);
        centerHit  = (digitalRead(ss8) == 0 || digitalRead(ss9) == 0 || digitalRead(ss10) == 0 || digitalRead(ss11) == 0);
      }

      if (turnPhase1) { // Giai đoạn 1: Quay tốc độ 55 đến khi vạch trượt ra mép ngoài
        analogWrite(PWM_T, 55); analogWrite(PWM_P, 55);
        if (oldEdgeHit || (millis() - stateTimer > 2500)) { // Có mốc thời gian 2.5s để bảo vệ tránh xe quay vòng tròn
          turnPhase1 = false; turnLineLost = false; stateTimer = millis();
        }
      } else if (!turnLineLost) { // Giai đoạn 2: Quay tốc độ 40 chờ vạch mới xuất hiện ở mép bên kia
        analogWrite(PWM_T, 40); analogWrite(PWM_P, 40);
        if (newEdgeHit || (millis() - stateTimer > 3000)) {
          turnLineLost = true;
        }
      } else { // Giai đoạn 3: Quay tốc chậm 30 đưa vạch mới vào tâm rồi phanh
        analogWrite(PWM_T, 30); analogWrite(PWM_P, 30);
        if (centerHit) {
          dongthang();
          analogWrite(PWM_T, 0); analogWrite(PWM_P, 0);
          delay(500);
          if (state == "toi") chieutien(); else chieului();
          lidar_bank0();
          Serial.println(F("[TURN L] Quay xong"));
          if (isAutoMode) deba(); else sysState = STATE_IDLE;
        }
      }
      break;
    }

    case STATE_TURNING_R:
    {
      if (digitalRead(CB_VACHAM) == 0) { dunglaigap(); sysState = STATE_OBSTACLE; return; }
      
      bool oldEdgeHit = false, newEdgeHit = false, centerHit = false;
      if (state == "toi") {
        oldEdgeHit = (digitalRead(ss1) == 0 || digitalRead(ss2) == 0);   // Vạch cũ chạm mép trái
        newEdgeHit = (digitalRead(ss15) == 0 || digitalRead(ss16) == 0); // Vạch mới chạm mép phải
        centerHit  = (digitalRead(ss8) == 0 || digitalRead(ss9) == 0 || digitalRead(ss10) == 0 || digitalRead(ss11) == 0);
      } else { // Khi đi lùi, đuôi xe quét ngược lại
        oldEdgeHit = (digitalRead(ss15) == 0 || digitalRead(ss16) == 0);
        newEdgeHit = (digitalRead(ss1) == 0 || digitalRead(ss2) == 0);
        centerHit  = (digitalRead(ss6) == 0 || digitalRead(ss7) == 0 || digitalRead(ss8) == 0 || digitalRead(ss9) == 0);
      }

      if (turnPhase1) { // Giai đoạn 1: Quay tốc độ 55
        analogWrite(PWM_T, 55); analogWrite(PWM_P, 55);
        if (oldEdgeHit || (millis() - stateTimer > 2500)) {
          turnPhase1 = false; turnLineLost = false; stateTimer = millis();
        }
      } else if (!turnLineLost) { // Giai đoạn 2: Quay tốc độ 40
        analogWrite(PWM_T, 40); analogWrite(PWM_P, 40);
        if (newEdgeHit || (millis() - stateTimer > 3000)) {
          turnLineLost = true;
        }
      } else { // Giai đoạn 3: Quay chậm đưa vào tâm
        analogWrite(PWM_T, 30); analogWrite(PWM_P, 30);
        if (centerHit) {
          dongthang();
          analogWrite(PWM_T, 0); analogWrite(PWM_P, 0);
          delay(500);
          if (state == "toi") chieutien(); else chieului();
          lidar_bank0();
          Serial.println(F("[TURN R] Quay xong"));
          if (isAutoMode) deba(); else sysState = STATE_IDLE;
        }
      }
      break;
    }
  }
}
void deba() {
  mothang();               // LUÔN mở phanh + bật RFID trước khi chạy
                           // (dunglaigap() trước đó đóng phanh — nếu không mở thì xe bị giữ)
  delay(500);             // Chờ thêm để đảm bảo phanh đã mở hoàn toàn
  sysState = STATE_RUNNING;
  initial_motor_speed = 10;
  batden_xanh_3thap();     // Đèn xanh: xe đang di chuyển
  Tat_cambienphat();       // Tắt cảm biến phát khi xe rời trạm sạc
  resetPID();              // Xóa tích lũy PID cũ để xe không bị giật/lệch khi bắt đầu chạy
}
void mothang() {
  //digitalWrite(BREAK12, HIGH); // ORG
  digitalWrite(BREAK12, LOW);
  bat_RFID();
}
void dongthang() { //
  //digitalWrite(BREAK12, LOW); // ORG
  digitalWrite(BREAK12, HIGH); 
  tat_RFID();
}
void dongthang_kotatRFID() 
{
  digitalWrite(BREAK12, LOW); // ORG
  digitalWrite(BREAK12, HIGH); 
  //tat_RFID();
}
void chieutien() {
  // Bật cảm biến hướng tiến (luôn đặt trước mọi thứ khác)
  digitalWrite(sstoi_0V, HIGH);
  digitalWrite(sstoi_24V, HIGH);
  digitalWrite(sslui_0V, LOW);
  digitalWrite(sslui_24V, LOW);

  // LUÔN reset chân CW motor về đúng chiều tiến
  // Bug sau quay: chieuqueotrai/phai_90() đặt CW sai cấu hình → nếu không reset
  // thì PID chạy motor sai chiều → xe lệch ngay khi bắt đầu di chuyển
  digitalWrite(CW_T, HIGH);  // CHAY TOI
  digitalWrite(CW_P, LOW);   // CHAY TOI

  if (state == "toi") return;  // Đã đúng hướng, không cần dừng/đổi chiều

  // Đang đi LÙI → phải dừng hẳn trước khi đảo chiều (bảo vệ hộp số)
  dunglaigap();
  state = "toi";
  delay(100);
}
void chieului() {
  // Bật cảm biến hướng lùi (luôn đặt trước mọi thứ khác)
  digitalWrite(sslui_0V, HIGH);
  digitalWrite(sslui_24V, HIGH);
  digitalWrite(sstoi_0V, LOW);
  digitalWrite(sstoi_24V, LOW);

  // LUÔN reset chân CW motor về đúng chiều lùi (lý do giống chieutien)
  digitalWrite(CW_T, LOW);   // CHAY LUI
  digitalWrite(CW_P, HIGH);  // CHAY LUI

  if (state == "lui") return;  // Đã đúng hướng, không cần dừng/đổi chiều

  // Đang đi TIẾN → phải dừng hẳn trước khi đảo chiều (bảo vệ hộp số)
  dunglaigap();
  state = "lui";
  delay(100);
}
void kiemtra_Lidar_dai() {
  if (state == "toi") {
    while (digitalRead(CBVC5) == 1) {
      //nhacstar();
      giaotiephmi();
      guithongtinloi_hmi("Xe kẹt, kiểm tra cảm biến trước");
      delay(5);  //chống CPU tràn
    }
    if (digitalRead(CBVC5) == 0) tatnhac();
  }
  if (state == "lui") {
    while (digitalRead(CBVC4) == 1) {
      //nhacstar();
      giaotiephmi();
      guithongtinloi_hmi("Xe kẹt, kiểm tra cảm biến sau");
      delay(5);  //chống CPU tràn
    }
    if (digitalRead(CBVC4) == 0) tatnhac();
  }
  // Thêm tắt nhạc nếu xong kiểm tra lidar dài
  tatnhac();
}
void tat_RFID() {
  Serial1.end();  // rfid
}
void bat_RFID() {
  Serial1.begin(9600);
  Serial1.setTimeout(50);               // Serial1.begin() reset timeout về 1000ms — phải set lại
  delay(50);                            // Chờ RFID reader ổn định sau khi reinit
  while (Serial1.available()) Serial1.read();  // Flush byte khởi động từ RFID (không có F → gây lỗi)
}
void chieuqueotrai_90() {
  // DAO CHIEU DC
  if (state == "toi") {
    digitalWrite(CW_T, HIGH);
    digitalWrite(CW_P, HIGH);
    delay(200);
    //Serial.println("chieu tien re trai");
  } else if (state == "lui") {
    digitalWrite(CW_T, HIGH);
    digitalWrite(CW_P, HIGH);
    delay(200);
    //Serial.println("chieu lui re trai");
  }
}
void chieuqueophai_90() {
  // DAO CHIEU DC
  if (state == "toi") {
    digitalWrite(CW_T, LOW);
    digitalWrite(CW_P, LOW);
    delay(200);
    //Serial.println("chieu tien re phai");
  } else if (state == "lui") {
    digitalWrite(CW_T, LOW);
    digitalWrite(CW_P, LOW);
    delay(200);
    //Serial.println("chieu lui re phai");
  }
}
void dunglai() {
  //initial_motor_speed=70;
  for (int k = 0; k < 10; k++) {
    read_sensor_values();
    docrfid();
    calculate_pid();
    motor_control();
    // vatcan(); // Đã xóa hàm vatcan cũ gây lỗi, logic vật cản đã chuyển sang updateAGV
    delay(5);
    if (k == 5) {
      initial_motor_speed = initial_motor_speed - 50;
      if (initial_motor_speed < speed_min) {
        initial_motor_speed = 0;
        k = 0;
        break;
      }
      k = 0;
    }
  }
  dongthang();
  analogWrite(PWM_T, 0);
  analogWrite(PWM_P, 0);
  //initial_motor_speed=speed_;
}
void dunglaigap() {
  analogWrite(PWM_T, 50);
  analogWrite(PWM_P, 50);  //50
  dongthang();
  analogWrite(PWM_T, 0);
  analogWrite(PWM_P, 0);
  delay(500);
}
void dunglaigap_kotatRFID()
{
  analogWrite(PWM_T, 50);
  analogWrite(PWM_P, 50); //50
  dongthang_kotatRFID();
  analogWrite(PWM_T, 0);
  analogWrite(PWM_P, 0);
  delay(300);
}

void dunglaimatline() {
  initial_motor_speed = 50;
  calculate_pid();
  motor_control();
  delay(200);
  dongthang();
  analogWrite(PWM_T, 0);
  analogWrite(PWM_P, 0);
  guithongtinloi_hmi("AGV bị lệch đường từ");
  delay(200);
  while (((digitalRead(ss1) == 1) && (digitalRead(ss2) == 1) && (digitalRead(ss3) == 1) && (digitalRead(ss4) == 1) && (digitalRead(ss5) == 1) && (digitalRead(ss6) == 1) && (digitalRead(ss7) == 1) && (digitalRead(ss8) == 1) && (digitalRead(ss9) == 1) && (digitalRead(ss10) == 1) && (digitalRead(ss11) == 1) && (digitalRead(ss12) == 1) && (digitalRead(ss13) == 1) && (digitalRead(ss14) == 1) && (digitalRead(ss15) == 1) && (digitalRead(ss16) == 1))) {
    analogWrite(PWM_T, 0);
    analogWrite(PWM_P, 0);
    guithongtinloi_hmi("Xe bị lệch đường từ");
    delay(200);
    giaotiephmi();
    nhacstop();
    // Serial.println("XE RA KHOI DUONG TU");
  }
  tatnhac();
  guithongtinloi_hmi(" ");
  delay(200);
  mothang();
  deba();
}
void batden_vang_3thap() {
  digitalWrite(dieukhien_denvang, HIGH);
  digitalWrite(dieukhien_denxanh, LOW);
}
void batden_xanh_3thap() {
  digitalWrite(dieukhien_denvang, LOW);
  digitalWrite(dieukhien_denxanh, HIGH);
}
void tatden_3thap() {
  digitalWrite(dieukhien_denvang, LOW);
  digitalWrite(dieukhien_denxanh, LOW);
}
void tocdomacdinh() {
  speed_max = number0 + 30;
  speed_min = 5;
  for (int i = 0; i < 20; i++) {
    //Serial.println("tangtoctutu");
    docrfid();
    if ((serNum0 != 0) && (serNum1 != 0) && (serNum2 != 0) && (serNum3 != 0)) break;  // Điều kiện này
    read_sensor_values();
    calculate_pid();
    motor_control();
    if (i == 3) {
      initial_motor_speed = initial_motor_speed + 30;
      if (initial_motor_speed >= int(number0)) {
        initial_motor_speed = int(number0);
        duytrigiamtoc = 0;
        i = 0;
        break;
      }
      i = 0;
    }
  }
  if ((!duytrigiamtoc)) { initial_motor_speed = number0; }
  duytrigiamtoc = 0;
  duytrigiamtoc2 = 0;
  lidar_bank0();
}
void tocdomacdinh_tb() {
  //ChophepQuay=1;  // mới chuyển cái này ra đây, lúc trước nó ở sau cùng của hàm deba()
  initial_motor_speed = number1;
}
void datlaitocdo() {
  tatvatcan = 0;
  duytrigiamtoc = 0;
  tocdomacdinh();
  tatnhac();
  clear_rifd();
}
void datlaitocdo_tb() {
  tatvatcan = 0;
  duytrigiamtoc = 1;
  tocdomacdinh_tb();
  clear_rifd();
}
void giamtoc_tutu() {
  for (int k = 1; k < 20; k++) {
    read_sensor_values();
    calculate_pid();
    motor_control();
    docrfid();
    if (k >= 2) {
      initial_motor_speed = initial_motor_speed - 20;
      if (initial_motor_speed < 10) {
        initial_motor_speed = 0;
        //Serial.println("DA GIAM VE 0");
        dongthang();
        break;
      }
    }
  }
}
void giamtoc_tutu_kotatRFID() 
{
  for (int k = 1; k < 20; k++) 
  {
    read_sensor_values();
    calculate_pid();
    motor_control();
    docrfid();
    if (k >= 2)
    {
      initial_motor_speed = initial_motor_speed - 20;
      if (initial_motor_speed < 10) 
      {
        initial_motor_speed = 0;
        //Serial.println("DA GIAM VE 0");
        dongthang_kotatRFID();
        break;
      }
    }
  }
}
void giamtoc_gap() {
  for (int k = 1; k < 20; k++) {
    read_sensor_values();
    calculate_pid();
    motor_control();
    docrfid();
    if (k >= 2) {
      initial_motor_speed = initial_motor_speed - 40;
      if (initial_motor_speed < 10) {
        initial_motor_speed = 0;
        //Serial.println("DA GIAM VE 0");
        dongthang();
        break;
      }
    }
  }
}
void kiemtraPin() {
  // ── Debounce 5ms ──────────────────────────────────────────────────────────
  bool raw = (digitalRead(PIN_PIN_YEU) == HIGH);
  static bool  last_raw       = false;
  static unsigned long db_start = 0;
  if (raw != last_raw) { db_start = millis(); last_raw = raw; }
  if (millis() - db_start < 5) return;  // Chưa ổn định

  bool newly_low      = (!battery_low && raw);   // Vừa chuyển khỏe → yếu
  bool newly_recovered = (battery_low && !raw);  // Vừa phục hồi (sạc xong)
  battery_low = raw;

  if (newly_low) {
    // Chỉ ghi log — KHÔNG hiển thị HMI/còi ngay, tránh làm phiền khi xe đang chạy
    // HMI + còi sẽ được bật khi battery_blocking=true (hành trình xong, về trạm)
    Serial.println(F("[BAT] Pin yeu phat hien (battery_low=true) — tiep tuc hanh trinh hien tai"));
  }

  if (newly_recovered) {
    // Pin phục hồi (tín hiệu cảm biến mất) — battery_blocking sẽ do Python clear qua battery_unlock
    Serial.println(F("[BAT] Tin hieu pin yeu da mat (battery_low=false)"));
    // KHÔNG tự clear battery_blocking — phải chờ Python xác nhận đã sạc đủ 2h
  }
}
void nhacstar()  // 001
{
  Serial.print(F("[AUDIO] nhacstar() called. number2=")); Serial.println(number2);
  if (((number2 == 1) && (mute == 0))) {
    //Serial.println("nhạc xin chú ý xe");
    digitalWrite(I_1, LOW);
    digitalWrite(I_stop, LOW);
    digitalWrite(I_start, HIGH);
  }
}
void nhacstop()  // 010
{
  Serial.print(F("[AUDIO] nhacstop() called. number2=")); Serial.println(number2);
  if ((number2 == 1) && (mute == 0)) {
    digitalWrite(I_1, LOW);
    digitalWrite(I_stop, HIGH);
    digitalWrite(I_start, LOW);
  }
}
void nhacdenline()  // 011
{
  Serial.print(F("[AUDIO] nhacdenline() called. number2=")); Serial.println(number2);
  if (number2 == 1) {
    //Serial.println("nhạc đến tổ");
    digitalWrite(I_1, LOW);
    digitalWrite(I_stop, HIGH);
    digitalWrite(I_start, HIGH);
  }
}
void nhacxincaplieu()  // 100
{
  Serial.print(F("[AUDIO] nhacxincaplieu() called. number2=")); Serial.println(number2);
  //Serial.println("nhạc cấp liệu");
  if (number2 == 1) {
    digitalWrite(I_1, HIGH);
    digitalWrite(I_stop, LOW);
    digitalWrite(I_start, LOW);
  }
}
void nhacpinyeu()  //101
{
  Serial.print(F("[AUDIO] nhacpinyeu() called. number2=")); Serial.println(number2);
  //Serial.println("nhạc cấp pin yếu");
  if (number2 == 1) {
    digitalWrite(I_1, HIGH);
    digitalWrite(I_stop, LOW);
    digitalWrite(I_start, HIGH);
  }
}
void nhacmocua()  //110
{
  Serial.print(F("[AUDIO] nhacmocua() called. number2=")); Serial.println(number2);
  //Serial.println("nhạc cxin mở cửa");
  if (number2 == 1) {
    digitalWrite(I_1, HIGH);
    digitalWrite(I_stop, HIGH);
    digitalWrite(I_start, LOW);
  }
}
void nhacxinre()  //111
{/*
  Serial.print(F("[AUDIO] nhacxinre() called. number2=")); Serial.println(number2);
  //Serial.println("nhạc cxin mở cửa");
  if (number2 == 1) {
    digitalWrite(I_1, HIGH);
    digitalWrite(I_stop, HIGH);
    digitalWrite(I_start, HIGH);
  }*/
}
void tatnhac() {
  Serial.println(F("[AUDIO] tatnhac() called."));
  digitalWrite(I_1, LOW);
  digitalWrite(I_stop, LOW);
  digitalWrite(I_start, LOW);
  //delay(100);
}
void giaotiephmi()  // qua cong serial 2
{
  nexLoop(nex_listen_list);  // Check for any touch event
}
void tat_giaotiephmi() {
  Serial2.end();
}
void bat_giaotiephmi() {
  Serial2.begin(9600);
}
void guitrangthai_hmi(String guichuoitrangthai_hmi) {
  giaotiephmi();
  //sendCommand("page 0"); // chuyen ve trang 0
  Serial2.print("t3.txt=");              // trang thai AGV
  Serial2.print("\"");                   // Since we are sending text, and not a number, we need to send double quote before and after the actual text.
  Serial2.print(guichuoitrangthai_hmi);  // This is the text you want to send to that object and atribute mentioned before.
  Serial2.print("\"");                   // Since we are sending text, and not a number, we need to send double quote before and after the actual text.
  Serial2.write(0xff);                   // We always have to send this three lines after each command sent to the nextion display.
  Serial2.write(0xff);
  Serial2.write(0xff);
  delay(100);
  giaotiephmi();
}
void guitrangthai_chuyenhmi(String guichuoitrangthai_hmi, int giatri_lx) {
  giaotiephmi();
  // Serial.println("Vào hàm hiện HMI");
  // Serial.print("Chuỗi:");
  // Serial.println(guichuoitrangthai_hmi);
  // Serial.print("Giá trị:");
  // Serial.println(giatri_lx);
  Serial2.print("t3.txt=");
  Serial2.print("\"");
  Serial2.print(guichuoitrangthai_hmi);
  Serial2.print(giatri_lx);  // Thêm giá trị l1, l2, l3...
  Serial2.print("\"");
  Serial2.write(0xff);
  Serial2.write(0xff);
  Serial2.write(0xff);
  delay(100);
  giaotiephmi();
}

void guithongtinloi_hmi(String guichuoiloi_hmi) {
  //sendCommand("page 0"); // chuyen ve trang 0
  giaotiephmi();
  Serial2.print("t5.txt=");        // trang thai AGV
  Serial2.print("\"");             // Since we are sending text, and not a number, we need to send double quote before and after the actual text.
  Serial2.print(guichuoiloi_hmi);  // This is the text you want to send to that object and atribute mentioned before.
  Serial2.print("\"");             // Since we are sending text, and not a number, we need to send double quote before and after the actual text.
  Serial2.write(0xff);             // We always have to send this three lines after each command sent to the nextion display.
  Serial2.write(0xff);
  Serial2.write(0xff);
  delay(100);
}
void docrfid()  // update 23.4// thiếu thông tin nếu vị trí của F lớn hơn 3.......................
{
  // Serial1.println("$S#");// gui yeu cau dau doc gui lại du lieu
  int checkSum_docrfid = 0;
  int check_coData = 0;
  int Temp_Sn0 = 0, Temp_Sn1 = 0, Temp_Sn2 = 0, Temp_Sn3 = 0;
  // QUAN TRỌNG: dùng if thay vì while để xử lý đúng 1 frame RFID mỗi lần gọi.
  // Nếu dùng while: khi xe đứng/chậm trên thẻ, đầu đọc gửi liên tục (cùng thẻ),
  // while không break → vòng lặp vô tận → PID/motor_control không được gọi → xe treo.
  // Frame tiếp theo sẽ được xử lý ở lần gọi docrfid() tiếp theo (mỗi vòng loop chính).
  if (Serial1.available() > 1) {
    check_coData = 1;
    errorDoc = 0;
    // size_t num_read = Serial1.readBytesUntil('\r', name_arr, sizeof(name_arr)-1 );
    size_t num_read = Serial1.readBytes(name_arr, sizeof(name_arr) - 1);
    name_arr[num_read] = '\0';
    Serial.println(name_arr);
    digitalWrite(denbao_RFID, HIGH);
    for (int i = 0; i < num_read - 3; i++)  // Binh update 19.9.24 for num_read. (trừ thêm 3 để bỏ 3 kí tự cuối)
    {
      if (name_arr[i] == 'F')
      {
        //Serial.println(i);
        if (i >= 4) errorDoc = 1;  //update 23.4// thiếu thông tin nếu vị trí của F lớn hơn 3......................
        // Lưu giá trị từ vị trí của ký tự 'F' vào các biến serNum0, serNum1, serNum2, serNum3
        Temp_Sn0 = name_arr[i + 12];
        Temp_Sn1 = name_arr[i + 13];
        Temp_Sn2 = name_arr[i + 14];
        Temp_Sn3 = name_arr[i + 15];
        // Thêm điều kiện mới chỉ xử lý thẻ 1 lần nhờ vào biến Temp_Sn0, nếu khác thì mới gán
        if ((Temp_Sn0 != Last_Sn0) || (Temp_Sn1 != Last_Sn1) || (Temp_Sn2 != Last_Sn2) || (Temp_Sn3 != Last_Sn3)) {
          Sn0 = Temp_Sn0;
          Sn1 = Temp_Sn1; 
          Sn2 = Temp_Sn2;
          Sn3 = Temp_Sn3;
        }
        checkSum_docrfid = checkSum_docrfid + 1;
      }
    }
    name_arr[0] = '0';
    if (((Sn0 != 0) || (Sn1 != 0) || (Sn2 != 0) || (Sn3 != 0)) && ((Temp_Sn0 != Last_Sn0) || (Temp_Sn1 != Last_Sn1) || (Temp_Sn2 != Last_Sn2) || (Temp_Sn3 != Last_Sn3))) {
      docthemoi = 1;
      serNum0 = Sn0 - 48;
      serNum1 = Sn1 - 48;
      serNum2 = Sn2 - 48;
      serNum3 = Sn3 - 48;
      
      // --- LOGIC MỚI: Cập nhật thẻ và gửi ngay lập tức ---
      int newTagValue = serNum0 * 1000 + serNum1 * 100 + serNum2 * 10 + serNum3;
      onNewTagDetected(newTagValue);
      // ------------------------------------------------

      Last_Sn0 = Temp_Sn0;
      Last_Sn1 = Temp_Sn1;
      Last_Sn2 = Temp_Sn2;
      Last_Sn3 = Temp_Sn3;
      String combinedStr = String(serNum0) + String(serNum1) + String(serNum2) + String(serNum3);
      Serial.print("New RFID: ");
      Serial.println(combinedStr);
      digitalWrite(denbao_RFID, LOW);
      // break không cần thiết — dùng if thay vì while, block tự kết thúc sau đây
      return;  // Thoát docrfid() ngay sau khi xử lý thẻ mới — cho phép PID chạy sớm hơn
    }
    digitalWrite(denbao_RFID, LOW);
    //update 23.4// thiếu thông tin nếu vị trí của F lớn hơn 3......................
    // rfidBadFrameCount: đếm frame lỗi liên tiếp, reset khi có frame tốt
    static uint8_t rfidBadFrameCount = 0;
    if (((checkSum_docrfid == 0) || (errorDoc == 1)) && (check_coData == 1))  //
    //if ((checkSum_docrfid==0)||(check_coData==1)||(errorDoc==1)) // nếu có data gửi từ đầu đọc rfid về và ko tìm thấy ký tự 'F' nào;
    {
      // Frame không hợp lệ — dùng counter để phân biệt lỗi thoáng qua vs. đầu đọc hỏng hẳn.
      // Lý do không while(1) ngay: bat_RFID() reinit Serial1 nên byte đầu tiên sau begin()
      // có thể không có 'F' (init byte) → không phải lỗi thật, bỏ qua là đúng.
      rfidBadFrameCount++;
      Serial.print(F("[RFID] Bad frame #")); Serial.println(rfidBadFrameCount);
      if (rfidBadFrameCount >= 10) {
        // 10 frame lỗi liên tiếp → đầu đọc thực sự có vấn đề
        rfidBadFrameCount = 0;
        dunglaigap();
        guithongtinloi_hmi("Loi dau doc the RFID");
        Serial.println(F("[RFID] 10 bad frames — dung xe, cho kiem tra dau doc"));
        sysState = STATE_IDLE;
      }
      return;  // Bỏ qua frame lỗi này, xử lý frame tiếp ở vòng lặp sau
    }
    rfidBadFrameCount = 0;  // Reset counter khi có frame tốt (có F, không errorDoc)
  }
}
void kiemtra_docrfid_JY() {
  // Serial1.println("$S#");// gui yeu cau dau doc gui lại du lieu
  while (Serial1.available() > 1) {
    // size_t num_read = Serial1.readBytesUntil('\r', name_arr, sizeof(name_arr)-1 );
    size_t num_read = Serial1.readBytes(name_arr, sizeof(name_arr) - 1);
    name_arr[num_read] = '\0';
    Serial.println(name_arr);
    //digitalWrite(denbao_mauxanh,HIGH);
    if (name_arr[0] == '$') {
      name_arr1[0] = name_arr[1];
      name_arr1[1] = name_arr[2];
      name_arr1[2] = name_arr[3];
      name_arr1[3] = name_arr[4];
      name_arr1[4] = name_arr[5];
      name_arr1[5] = name_arr[6];
      name_arr1[6] = name_arr[7];
      name_arr1[7] = name_arr[8];
      name_arr1[8] = name_arr[9];
      name_arr1[9] = name_arr[10];
      name_arr1[10] = name_arr[11];
      name_arr1[11] = name_arr[12];
      name_arr1[12] = name_arr[13];
      name_arr1[13] = name_arr[14];
      name_arr1[14] = name_arr[15];
      name_arr1[15] = name_arr[16];
      name_arr1[16] = name_arr[17];
      name_arr1[17] = name_arr[18];
      String str((char *)name_arr1);
      Serial.print(name_arr1[12], DEC);
      Serial.print(", ");
      Serial.print(name_arr1[13], DEC);
      Serial.print(", ");
      Serial.print(name_arr1[14], DEC);
      Serial.print(", ");
      Serial.print(name_arr1[15], DEC);
      Sn0 = name_arr1[12];
      Sn1 = name_arr1[13];
      Sn2 = name_arr1[14];
      Sn3 = name_arr1[15];
      name_arr[0] = '0';
      while (1) {
        guithongtinloi_hmi("Đầu đọc thẻ sẵn sàng");
        delay(200);
        giaotiephmi();
        delay(1000);
        guithongtinloi_hmi(" ");
        delay(200);
        tatnhac();
        demthoat = 1;
        clear_rifd();
        break;
      }
      // Serial1.println("$S#");
    } else {
      while (1) {
        guithongtinloi_hmi("Đầu đọc thẻ sẵn sàng");
        delay(200);
        giaotiephmi();
        delay(1000);
        guithongtinloi_hmi(" ");
        delay(200);
        tatnhac();
        demthoat = 1;
        clear_rifd();
        break;
      }
    }
  }
}
void clear_rifd() {
  serNum0 = 0;
  serNum1 = 0;
  serNum2 = 0;
  serNum3 = 0;
  duytri_queophai = 0;
  duytri_queotrai = 0;
  digitalWrite(denbao_RFID, LOW);
}
void tatgiaotiep_ESP() 
{
  UART_ESP.end();
}
void batgiaotiep_ESP()
{
  UART_ESP.begin(115200);
}
void Cho_tin_hieuESP() 
{
}
void reset_ESP32() 
{
  digitalWrite(spare_X2, HIGH);
  delay(5000);
  digitalWrite(spare_X2, LOW);
}
//lap
void loop()
{
  // --- XỬ LÝ JSON ---
  listenJson();
  if (millis() - lastPublishJson > 1000) { // Gửi trạng thái heartbeat mỗi 1000ms
    publishJson();
    lastPublishJson = millis();
    Serial.print(F("[DBG] freeRam="));
    Serial.println(freeRam());
  }
  // ------------------

#ifdef ENABLE_BATTERY_SENSOR
  // --- KIỂM TRA MỨC PIN (mỗi 500ms để tránh nhiễu) ---
  static unsigned long lastBatCheck = 0;
  if (millis() - lastBatCheck >= 500) {
    lastBatCheck = millis();
    kiemtraPin();
  }
#endif

  // --- CẬP NHẬT TRẠNG THÁI AGV ---
  updateAGV();

#ifdef ENABLE_BATTERY_SENSOR
  // --- PHÁT HIỆN: pin yếu + hành trình kết thúc → chuyển sang battery_blocking ---
  // Trong lúc xe đang chạy: battery_low=true nhưng KHÔNG chặn (hành trình tiếp tục bình thường)
  // Khi về trạm / hết plan: mới kích hoạt battery_blocking để chặn lệnh mới
  {
    bool mission_done = (sysState == STATE_IDLE &&
                         (missionLength == 0 || currentMissionIndex >= missionLength));
    if (battery_low && mission_done && !battery_blocking) {
      battery_blocking = true;
      pendingEvent     = "battery_need_charge";
      guithongtinloi_hmi("Pin yeu — dang cho sac");
      nhacpinyeu();
      Serial.println(F("[BAT] Hanh trinh xong + pin yeu → battery_blocking=true, cho Python dieu ve tram sac"));
    }
  }
#endif

  giaotiephmi();
  // Đã xóa toàn bộ logic vòng lặp cũ.
  // Loop giờ đây rất sạch, chỉ chờ lệnh JSON hoặc chạy Auto.
}
