# PyNote — Kịch bản thuyết trình (Tiếng Việt, bản chuyên sâu)

Kịch bản cho `pynote-rag-teachin.html` (27 slide). Độ dài nói khoảng
**20–24 phút** với tốc độ vừa phải. Nếu bị giới hạn thời gian, có thể cắt các
slide đánh dấu *(có thể lược bỏ)* và rút gọn phần cơ chế chi tiết ở mỗi slide.

Mỗi mục dưới đây tương ứng một slide. Câu in *nghiêng* là chỉ dẫn sân khấu,
không đọc. Thuật ngữ chuyên ngành giữ nguyên tiếng Anh (chunk, embedding,
retrieval…) theo thông lệ, kèm giải thích tiếng Việt ở lần xuất hiện đầu.

---

## Slide 1 — Trang bìa: From PDF to Cited Answer

Em chào thầy/cô và các bạn. Em là Hùng. Hôm nay em xin trình bày về PyNote —
một hệ thống **Retrieval-Augmented Generation**, viết tắt là RAG, mà em xây
dựng để trả lời câu hỏi trên tài liệu PDF. Điểm khác biệt quan trọng nhất của
hệ thống là: mọi câu trả lời đều kèm **trích dẫn được kiểm chứng đến từng ký
tự** so với tài liệu gốc — tức là người dùng có thể bấm vào một trích dẫn và
nhảy đến đúng câu văn trong file PDF. Sơ đồ ở cuối slide chính là bốn giai
đoạn em sẽ đi qua hôm nay: phân tích tài liệu, mã hóa vector, truy hồi, và
sinh câu trả lời có căn cứ.

## Slide 2 — Dàn bài báo cáo

Báo cáo gồm sáu phần. Phần một là bối cảnh: vì sao mô hình ngôn ngữ lớn cần
đến truy hồi thông tin. Phần hai và ba là hai nửa của hệ thống: pipeline nạp
tài liệu (ingestion) và pipeline truy vấn (query). Phần bốn nói về việc ràng
buộc mô hình chỉ trả lời từ bằng chứng, và cơ chế kiểm chứng trích dẫn. Phần
năm giới thiệu ba framework hỗ trợ: LangChain/LangGraph, LangSmith và Ragas.
Phần cuối là đánh giá: em đối chiếu hệ thống của mình với một kiến trúc RAG
tham chiếu đầy đủ, và tự chỉ ra các hạn chế một cách trung thực.

## Slide 3 — Đặt vấn đề

Trước hết là bài toán. Mô hình ngôn ngữ lớn có ba hạn chế cốt lõi đối với
nhiệm vụ này. Thứ nhất, **knowledge cutoff** — dữ liệu huấn luyện dừng ở một
thời điểm cố định; tài liệu nội bộ hoặc mới phát hành đơn giản là không nằm
trong mô hình, và không thể "dạy lại" mô hình mỗi khi có tài liệu mới vì chi
phí fine-tune rất lớn. Thứ hai, **giới hạn context window** — một tài liệu ba
trăm trang không thể nhét vào prompt; kể cả khi context đủ dài, chi phí token
và hiện tượng "lost in the middle" — mô hình bỏ sót thông tin ở giữa ngữ cảnh
dài — khiến cách làm này kém hiệu quả. Thứ ba, **hallucination** — khi bị hỏi
vượt quá hiểu biết, mô hình vẫn sinh văn bản trôi chảy nhưng không có căn cứ,
và nếu không có nguồn dẫn thì người đọc không thể phân biệt đúng sai. RAG giải
quyết cả ba: truy hồi các đoạn văn liên quan trước, rồi **ràng buộc** mô hình
chỉ được trả lời dựa trên các đoạn đó.

## Slide 4 — Tổng quan phương pháp

Đây là RAG trong một sơ đồ. Câu hỏi đi vào, hệ thống tìm kiếm trên chỉ mục
tài liệu, lấy các đoạn văn phù hợp nhất, đưa chúng vào prompt cùng chỉ thị
"chỉ trả lời từ bằng chứng này". Ba điểm cần ghi nhớ. **Nguyên lý**: mô hình
không cần *chứa* dữ liệu — nó chỉ cần dữ liệu phù hợp *nằm trong prompt* đúng
lúc; nói cách khác, ta biến bài toán "kiến thức" thành bài toán "tìm kiếm".
**Thách thức**: toàn bộ các khâu phía trước mô hình — parsing, chunking, đánh
chỉ mục, chất lượng tìm kiếm — quyết định **trần chất lượng** của mọi câu trả
lời; mô hình giỏi đến đâu cũng không cứu được nếu truy hồi sai đoạn văn.
**Lợi ích**: câu trả lời trở nên **kiểm toán được** — mọi khẳng định truy
ngược về một đoạn văn nguồn mà con người có thể tự kiểm tra.

## Slide 5 — Hệ thống: PyNote

PyNote hiện thực hóa phương pháp trên thành một ứng dụng web hoàn chỉnh,
tương tự về ý tưởng với NotebookLM của Google. Người dùng tải PDF lên, đặt
câu hỏi trong giao diện chat, và bấm vào bất kỳ trích dẫn nào để mở trình xem
PDF tại đúng câu được tô sáng. Về mặt kỹ thuật: quá trình nạp tài liệu chạy
nền bằng hàng đợi công việc nên không chặn người dùng; chat stream từng token
theo thời gian thực qua Server-Sent Events; hệ thống hỗ trợ đa tổ chức với
xác thực phân quyền; và có một bộ đánh giá tự động đóng vai trò "cổng chặn" —
nếu chất lượng trích dẫn giảm dưới ngưỡng thì không được triển khai phiên bản
mới.

## Slide 6 — Sơ đồ use case

Đây là góc nhìn use case. Có hai tác nhân con người: **nhà nghiên cứu** — tải
tài liệu, đặt câu hỏi, bấm trích dẫn, tìm kiếm; và **quản trị viên tổ chức**
— quản lý notebook và thành viên. Tác nhân thứ ba là **worker chạy nền**. Xin
lưu ý các quan hệ nét đứt: hành động tải tài liệu *kích hoạt* chuỗi
parse–chunk–embed, chuỗi này *sau đó* sinh ra dàn ý và câu hỏi gợi ý. Hai use
case được tô màu cam — đặt câu hỏi và bấm trích dẫn — là giá trị cốt lõi của
hệ thống.

## Slide 7 — Kiến trúc hệ thống

Kiến trúc gồm ba tầng. Tầng client là ứng dụng Next.js. Tầng backend gồm máy
chủ FastAPI — ủy quyền phần chat cho một pipeline LangGraph — và một worker
xử lý công việc nạp tài liệu qua hàng đợi Redis. Tầng dữ liệu được thiết kế
**tối giản có chủ đích**: một cơ sở dữ liệu Postgres duy nhất chứa cả vector
(qua extension pgvector), chỉ mục từ khóa (tsvector), bảng nghiệp vụ, và
trạng thái hội thoại. Lợi ích của quyết định này: phép **hợp nhất kết quả
tìm kiếm diễn ra trong một câu SQL duy nhất**, không phải đồng bộ hai kho dữ
liệu, không có độ trễ mạng giữa hai hệ thống, và tính nhất quán giao dịch có
sẵn. Bên phải là các dịch vụ ngoài: Claude cho khâu sinh câu trả lời là bắt
buộc; còn reranker Voyage, mô hình Gemini cho dàn ý, và LangSmith đều **tùy
chọn** — hệ thống suy giảm nhẹ nhàng khi thiếu, chứ không hỏng.

## Slide 8 — Hai pipeline: nạp tài liệu & truy vấn

Một nguyên tắc thiết kế quan trọng: có hai pipeline với yêu cầu rất khác
nhau. Pipeline **ingestion** chạy một lần cho mỗi tài liệu, ngoại tuyến,
trong worker — nó được phép chậm và kỹ lưỡng. Pipeline **query** chạy cho
từng câu hỏi khi người dùng đang chờ — từng mili-giây và từng token đều có
giá. Từ đó rút ra: **chất lượng câu trả lời được quyết định lúc nạp tài
liệu; độ trễ được quyết định lúc truy vấn** — và hai mối quan tâm này được
thiết kế tách bạch. Em sẽ trình bày theo đúng thứ tự đó.

## Slide 9 — Pipeline nạp tài liệu: tổng quan

Đây là pipeline ingestion từ đầu đến cuối. PDF được tải lên kho lưu trữ đối
tượng; bộ parser sinh ra văn bản sạch theo từng trang kèm vị trí các đề mục;
bộ chunker cắt văn bản thành các đơn vị truy hồi; bộ embedder biến mỗi chunk
thành một vector; tất cả được ghi vào bảng chunk với hai loại chỉ mục. Hai
bất biến xuyên suốt: thứ nhất, **mọi sản phẩm trung gian đều giữ offset ký tự
trỏ về cha của nó** — đây chính là sợi chỉ mà cơ chế trích dẫn lần ngược về
sau; thứ hai, **mọi công việc đều idempotent** — chạy lại một job sẽ xóa và
dựng lại đúng phần đầu ra của nó, nên việc nạp lại tài liệu luôn an toàn,
không tạo bản ghi trùng.

## Slide 10 — Bước 1: Parsing và chuẩn hóa

Bước một, parsing. Em dùng PyMuPDF trích xuất văn bản theo từng trang, sau đó
áp hai phép chuẩn hóa. Một: **loại bỏ header/footer lặp** — các dòng ở mép
trang xuất hiện trên hơn sáu mươi phần trăm số trang, như tiêu đề chạy và số
trang, được phát hiện bằng thống kê (sau khi gộp chữ số về một ký hiệu chung
để "Trang 3" và "Trang 4" được coi là cùng một mẫu) rồi loại bỏ — nếu giữ
lại, chúng sẽ nhiễm vào embedding của *mọi* chunk và làm nhiễu tìm kiếm.
Hai: **nối từ bị ngắt dòng bằng dấu gạch** — "improve-ment" thành
"improvement" — vì một từ bị cắt đôi là vô hình với cả tìm kiếm từ khóa lẫn
vector. Cuối cùng, các **đề mục được phát hiện từ metadata phông chữ** — em
trình bày ngay sau đây. Mọi khâu phía sau đều thừa hưởng chất lượng parsing,
nên việc chuẩn hóa được làm một lần, cẩn thận, ngay lúc nạp.

## Slide 11 — Phát hiện đề mục

Phát hiện đề mục hoạt động thuần túy bằng **thống kê phông chữ** — không cần
machine learning, không thêm thư viện nặng nào. Định nghĩa: cỡ chữ thân bài
là cỡ chữ **mang nhiều ký tự nhất** trong toàn tài liệu — dùng trọng số theo
số ký tự chứ không đếm số dòng, để vài dòng tiêu đề to không lấn át. Một dòng
được coi là đề mục nếu nó **ngắn** — dưới một trăm ký tự — và được đặt ở cỡ
chữ **lớn hơn thân bài ít nhất mười hai phần trăm**, hoặc in đậm ở cỡ thân
bài (có kiểm tra chống trường hợp cả tài liệu in đậm). Các cỡ chữ đề mục khác
nhau được xếp hạng thành cấp bậc: phông lớn nhất là cấp một, tương tự chương
— mục — tiểu mục. Đầu ra quan trọng nhất là **offset ký tự** của từng đề mục
trong văn bản đã làm sạch, vì offset đó trở thành **ranh giới cứng** cho bộ
chunker ở bước kế tiếp.

## Slide 12 — Bước 2: Chunking nhận biết cấu trúc

Bước hai, chunking — cắt tài liệu thành các đơn vị truy hồi cỡ ba trăm token,
tương đương khoảng một nghìn hai trăm ký tự tiếng Anh. Vì sao phải chunk?
Embedding hoạt động tốt nhất trên đoạn văn ngắn và tập trung, và prompt chỉ
chứa được số đoạn hữu hạn. Bộ chunker của em **cắt theo ngữ nghĩa thay vì
đếm ký tự mù quáng**, theo ba tầng ưu tiên: các đoạn văn — phân tách bằng
dòng trống — được gom tham lam đến kích thước mục tiêu; đoạn văn nào quá lớn
thì tách tại **ranh giới câu**, không bao giờ đứt giữa ý; và **không chunk
nào được vượt qua ranh giới đề mục**, nên một kết quả truy hồi không bao giờ
trộn nội dung của hai mục khác nhau. Phần đuôi quá ngắn được gộp vào chunk
trước thay vì bị vứt bỏ — không mất dữ liệu. Bất biến ở cuối slide là điều em
gọi là **hợp đồng trích dẫn**: `source_text[char_start:char_end] ==
chunk.text` — mỗi chunk là một lát cắt *chính xác tuyệt đối* của trang gốc.
Khoảng một nghìn ba trăm bài kiểm thử ngẫu nhiên hóa đảm bảo tính chất này,
vì nếu nó vỡ, trích dẫn sẽ trỏ sai chữ.

## Slide 13 — Bước 3: Embedding ngữ nghĩa

Bước ba, embedding. Mỗi chunk được ánh xạ thành một vector **384 chiều** bằng
mô hình BGE-small, chạy **cục bộ trên CPU** qua ONNX — không tốn chi phí API,
không gửi dữ liệu ra ngoài. Trực giác: các văn bản gần nghĩa nhau sẽ nằm gần
nhau trong không gian vector, nên "ô tô" tìm được "xe hơi" dù không trùng từ.
Hai chi tiết kỹ thuật đáng nói. Một: BGE là mô hình **bất đối xứng** — câu
truy vấn được thêm một tiền tố chỉ thị mà văn bản tài liệu không có; điều này
cải thiện độ khớp đo được, và chỉ ảnh hưởng phía truy vấn nên không phải
embedding lại kho dữ liệu. Hai: em dùng **contextual embeddings** — văn bản
đưa vào embedder được ghép thêm tiêu đề tài liệu và đường dẫn mục, ví dụ
"Attention Is All You Need › 3 Methods › 3.2 Training", nhưng **văn bản lưu
trong chunk vẫn là bản gốc** — nhờ vậy chunk mang theo danh tính tài liệu và
vị trí của nó vào không gian vector, mà hợp đồng trích dẫn không hề bị đụng
đến. Đây là kỹ thuật được Anthropic báo cáo giảm tới ba mươi lăm phần trăm
lỗi truy hồi khi kết hợp với hybrid search.

## Slide 14 — Bước 4: Lưu trữ và đánh chỉ mục

Lưu trữ: một bảng, hai chỉ mục. Chỉ mục **dense** là HNSW trên cột vector,
tìm theo khoảng cách cosine — HNSW là đồ thị phân tầng cho phép tìm hàng xóm
gần đúng trong thời gian gần logarit, đủ tốt đến cỡ một triệu chunk. Chỉ mục
**sparse** là tsvector có trọng số với chỉ mục GIN — tìm kiếm toàn văn cổ
điển. Vì sao cần cả hai? Vector bắt được **cách diễn đạt khác nhau** của cùng
một ý; từ khóa bắt được **thuật ngữ chính xác** — mã sản phẩm, tên riêng, từ
viết tắt — thứ mà embedding thường xử lý kém. Về trọng số: thân bài được đánh
trọng số A, còn tiêu đề cộng đường dẫn mục ở trọng số B — nghĩa là khớp trong
nội dung thực luôn thắng khớp trong đề mục.

## Slide 15 — Pipeline truy vấn (LangGraph)

Chuyển sang phía truy vấn. Pipeline là một **máy trạng thái bốn nút** hiện
thực bằng LangGraph: rewrite, retrieve, generate, và map-citations. Trạng
thái kiểu hóa chảy qua các nút; mỗi nút làm đúng một việc và trả về phần thay
đổi. Ba tính chất vận hành: **checkpoint** — mỗi lượt hội thoại được lưu vào
Postgres theo khóa thread, nên tải lại trang là cuộc hội thoại tái hiện
nguyên vẹn, kèm cả trích dẫn của từng tin nhắn; **streaming** — token chảy về
trình duyệt qua Server-Sent Events ngay khi đồ thị còn đang chạy, người dùng
thấy câu trả lời được viết ra theo thời gian thực; và **connection pooling**
— đồ thị được mở một lần cho cả tiến trình API, không trả chi phí thiết lập
kết nối cho từng yêu cầu.

## Slide 16 — Viết lại truy vấn

Nút đầu tiên giải quyết một vấn đề nhỏ nhưng quan trọng: **câu hỏi nối
tiếp**. Nếu người dùng hỏi "nói thêm về cái thứ hai đi", đem chuỗi đó đi tìm
kiếm thì không ra gì cả — cả vector lẫn từ khóa đều bất lực với đại từ. Giải
pháp: một mô hình rẻ đọc lịch sử hội thoại và viết lại câu hỏi thành một
**truy vấn độc lập**, giữ nguyên mọi thuật ngữ, con số, tên mục có ích cho
tìm kiếm. Thiết kế theo nguyên tắc **best-effort**: lượt đầu tiên đi thẳng
không tốn lời gọi mô hình nào; và bất kỳ lỗi nào — hết hạn mức, timeout — đều
rơi về dùng câu hỏi gốc. Nút rewrite có thể *cải thiện* một lượt chat, nhưng
được đảm bảo không bao giờ *làm hỏng* lượt nào.

## Slide 17 — Truy hồi lai với RRF

Nút retrieve chạy **tìm kiếm lai trong một câu SQL duy nhất**, dạng CTE.
Nhánh dense xếp hạng chunk theo khoảng cách cosine với vector truy vấn; nhánh
sparse xếp hạng theo độ khớp toàn văn. Hai danh sách được hợp nhất bằng
**Reciprocal Rank Fusion** — công thức trên slide: điểm của mỗi chunk là tổng
của một phần *(60 cộng thứ hạng)* trên từng danh sách. Vì sao dùng thứ hạng
thay vì điểm số? Vì độ tương đồng cosine và điểm ts_rank nằm trên hai thang
đo **không thể so sánh trực tiếp** — nhưng thứ hạng thì so được. Hằng số sáu
mươi là giá trị chuẩn từ bài báo gốc: nó làm mềm chênh lệch giữa hạng một và
hạng mười, để không danh sách nào lấn át. Kết quả: chunk đứng cao ở **một
trong hai** danh sách đều nổi lên. Một chi tiết bảo mật: mọi nhánh đều lọc
`notebook_id` ngay từ đầu — **cách ly dữ liệu giữa các tổ chức nằm ngay trong
câu truy vấn**, không phải lớp kiểm tra gắn thêm bên ngoài.

## Slide 18 — Phễu truy hồi

Truy hồi được tổ chức như một **cái phễu**: năm mươi ứng viên từ tìm kiếm
lai, thu hẹp còn mười hai bằng reranker, rồi khử trùng lặp và đóng gói còn
**tám chunk** đến tay mô hình. Lô-gích kinh tế là điểm mấu chốt: mỗi tầng
chi *nhiều tính toán hơn trên ít phần tử hơn*. SQL chấm điểm hàng nghìn chunk
bằng phép so vector rẻ; còn reranker Voyage là một **cross-encoder** — nó đọc
*cặp đầy đủ* câu-hỏi-nhân-chunk qua một lượt mô hình, chính xác hơn hẳn phép
so cosine hai vector độc lập, nhưng đắt — nên chỉ được dùng cho năm mươi ứng
viên đầu. Bước khử trùng lặp loại các chunk chồng lấn nhau trên cùng đoạn
văn (hệ quả của cửa sổ trượt), để tám suất cuối không lãng phí vào nội dung
lặp. Và cái phễu **hỏng theo hướng mở**: không có khóa Voyage thì hệ thống bỏ
qua rerank và đóng gói thẳng kết quả hybrid tốt nhất.

## Slide 19 — Sinh câu trả lời có căn cứ

Khâu generate. Tám chunk được đưa cho Claude dưới dạng khối nội dung
`search_result` **chính chủ** — và **Citations API** của Anthropic sẽ đánh
dấu *ký tự nào của chunk nào* chống lưng cho *từng câu* trong câu trả lời —
một cách tự nhiên ở tầng mô hình, chứ không phải bóc tách văn bản bằng regex
sau khi sinh. System prompt ràng buộc: "chỉ trả lời từ kết quả tìm kiếếm được
cung cấp; nếu không có thì nói thẳng". Về chi phí và độ trễ, em dùng **prompt
caching**: đặt điểm neo cache trên system prompt và phần lịch sử ổn định —
phần tiền tố này được cache giữa các lượt chat, chỉ có kết quả tìm kiếm mới
và câu hỏi mới phải trả giá đầy đủ; với hội thoại dài, tiết kiệm là đáng kể.
Lịch sử gửi cho mô hình được cắt còn mười hai tin nhắn cuối, căn vào lượt
người dùng để không vỡ cache — còn lịch sử đầy đủ vẫn nằm trong checkpoint
cho giao diện. Và khi bằng chứng không đủ, hành vi đúng là hành vi trung
thực: hệ thống trả lời "không tìm thấy trong tài liệu".

## Slide 20 — Kiểm chứng trích dẫn

Slide này là trái tim của độ tin cậy. Claude trả trích dẫn về dưới dạng
**offset ký tự** trong các chunk. Vì chunk đã giữ offset gốc từ lúc parsing —
nhớ lại hợp đồng trích dẫn — các offset này **ghép nối được** ngược về tận
trang PDF: hệ thống cắt lại đúng lát văn bản nguồn và **so sánh chuỗi chính
xác** với đoạn Claude tuyên bố đã trích. Khớp thì trích dẫn được gắn vào câu
trả lời; lệch thì bị đánh dấu và đo đếm. Trên giao diện, bấm một trích dẫn
là trình xem PDF mở ra với đúng câu văn được tô sáng bằng CSS Custom
Highlight API. Nguyên tắc: **trích dẫn được kiểm chứng, không được tin
suông** — và tính chất này chính là chỉ số đánh giá chủ đạo ở phần sau.

## Slide 21 — Các framework hỗ trợ *(có thể lược bỏ)*

Ba framework hỗ trợ hệ thống, mỗi cái một vai trò tách bạch — và em muốn nhấn
mạnh sự tách bạch này vì ba cái tên hay bị nhầm là một. **LangChain và
LangGraph** là tầng *điều phối*: LangChain cung cấp lớp bọc mô hình và kiểu
tin nhắn chuẩn; LangGraph biến pipeline thành đồ thị trạng thái có
checkpoint — nhờ nó mà hội thoại nhiều lượt được lưu bền miễn phí.
**LangSmith** là tầng *quan sát*: chỉ cần đặt biến môi trường, mọi lần chạy
nút, mọi prompt, độ trễ, số token đều được ghi vết lên dashboard — khi một
câu trả lời tệ, em mở trace và thấy ngay retriever trả về gì, prompt gửi đi
ra sao. **Ragas** là tầng *đánh giá*: dùng mô hình lớn làm giám khảo chấm các
chỉ số như faithfulness — mức độ câu trả lời chỉ nói điều ngữ cảnh chống lưng
— và answer relevancy. Tóm gọn: LangGraph **chạy**, LangSmith **quan sát**,
Ragas **chấm điểm**.

## Slide 22 — Phương pháp đánh giá

Đánh giá. Chỉ số chủ đạo là **citation grounding**: tỷ lệ trích dẫn mà phép
đối chiếu offset ký tự khớp tuyệt đối. Triển khai yêu cầu **tối thiểu 0,90**
— đây là "cổng chặn" tự động. Bên cạnh đó có hai lớp bổ trợ: các chỉ số
**lite** — xấp xỉ faithfulness và relevancy bằng độ trùng từ, không tốn lời
gọi mô hình nào, dùng cho vòng lặp tinh chỉnh nhanh, ví dụ khi dò tham số
top-k; và **Ragas đầy đủ** với giám khảo LLM cho phân tích sâu, để ở dạng
tùy chọn vì phụ thuộc nặng. Em cũng xin nêu thẳng hạn chế đã biết: bộ câu hỏi
vàng hiện chỉ có **mười câu** — đủ làm smoke test, nhưng quá nhỏ để phát hiện
suy thoái một cách tin cậy, vì một câu đổi kết quả là điểm số dao động mười
phần trăm. Mở rộng bộ này lên năm mươi đến một trăm câu là bước tiếp theo rẻ
nhất và giá trị nhất.

## Slide 23 — Kiến trúc tham chiếu: bản đồ RAG đầy đủ

Để đánh giá hệ thống một cách khách quan, em đối chiếu nó với một kiến trúc
tham chiếu — "bản đồ đầy đủ" của một hệ RAG hoàn chỉnh, gồm chín khối từ
nguồn dữ liệu, xử lý nạp, tầng lưu trữ, phễu truy hồi, cho đến động cơ suy
luận, kiểm định con người, đánh giá liên tục và kiểm thử đối kháng. Chấm màu
trên mỗi khối là hiện trạng của PyNote: xanh là đã làm tốt, cam là một phần,
đỏ là chưa có. Nhìn tổng thể có thể thấy ngay quy luật: **phần lõi giữa bản
đồ mạnh, phần vành đai xung quanh còn thiếu** — slide sau em phân tích chi
tiết.

## Slide 24 — Phân tích so sánh

Chi tiết. **Đã có**: phễu truy hồi lai đầy đủ; tầng dữ liệu hợp nhất; trích
dẫn được kiểm chứng — điểm này vượt phần lớn thiết kế tham chiếu; cổng đánh
giá tự động; và nạp tài liệu nhận biết cấu trúc. **Chưa có**: động cơ suy
luận — pipeline hiện cố định và tuyến tính, chưa có định tuyến (bỏ qua truy
hồi cho câu xã giao), chưa có phân rã câu hỏi nhiều bước, chưa có cơ chế tự
sửa khi truy hồi yếu; vòng phản hồi người dùng — chưa có nút thích/không
thích nên hệ thống không học được gì từ sử dụng thực; kiểm thử đối kháng —
prompt injection qua PDF tải lên là bề mặt tấn công **có thật nhưng chưa được
kiểm thử**, vì nội dung chunk chảy thẳng vào prompt; nguồn dữ liệu mới chỉ
có PDF; và đánh giá mới chạy trước khi triển khai, chưa liên tục trên lưu
lượng thật. Kết luận của em: **pipeline lõi đã hoàn chỉnh và được kiểm thử;
các vòng điều khiển bao quanh là việc tương lai.**

## Slide 25 — Nghiên cứu tình huống: chunking nhận biết cấu trúc

Một cải tiến cụ thể em vừa hoàn thành minh họa cho quy trình phát triển.
**Trước**: chunk là cửa sổ mù một nghìn hai trăm ký tự, cắt giữa câu, giữa
chủ đề, xuyên qua ranh giới mục; phần đuôi ngắn bị âm thầm vứt bỏ. **Sau**:
gom theo đoạn văn, tách theo câu, đề mục là ranh giới cứng; đường dẫn mục
được lưu vào metadata *và* nhúng vào vector; đuôi ngắn được gộp lại, không
mất chữ nào. Phương pháp là một chuỗi nhân quả: thống kê phông chữ → đề mục
→ ranh giới → chunk → đường dẫn mục → ngữ cảnh trong embedding. Kiểm định:
mười ba bài test mới, kiểm tra hợp đồng trích dẫn ngẫu nhiên hóa với ranh
giới ngẫu nhiên, và một migration cơ sở dữ liệu; tài liệu cũ cần nạp lại để
hưởng lợi.

## Slide 26 — Hướng phát triển

Hướng phát triển, theo thứ tự ưu tiên có chủ đích. Một: **mở rộng bộ câu hỏi
vàng** lên năm mươi đến một trăm câu — mọi cải tiến khác đều không đo lường
an toàn được nếu thiếu nó, nên nó đứng đầu dù không hào nhoáng. Hai: **định
tuyến nhẹ** — bỏ qua truy hồi cho câu không phải câu hỏi, thử lại khi truy
hồi yếu; giảm chi phí và tăng chất lượng cùng lúc. Ba: **thu phản hồi người
dùng** — dữ liệu đánh giá liên tục miễn phí từ sử dụng thực. Bốn: **kiểm thử
prompt injection** cho PDF tải lên. Năm: **mở rộng nguồn dữ liệu** — OCR,
Markdown, web — và trích xuất bảng biểu đúng nghĩa, phần việc còn lại của
khâu nạp tài liệu.

## Slide 27 — Kết luận

Xin kết luận bằng ba phát hiện từ quá trình xây dựng hệ thống. Thứ nhất,
**truy hồi chặn trần chất lượng câu trả lời** — mô hình không bao giờ giỏi
hơn những gì nó được cho xem. Thứ hai, **cấu trúc thắng cửa sổ cố định** —
tôn trọng đoạn văn, câu, và đề mục là nâng cấp rẻ mà hiệu quả so với cắt
mù. Thứ ba, **đánh giá phải gác cổng triển khai** — một chỉ số đo được như
citation grounding là thứ biến "có vẻ chạy được" thành một khẳng định kỹ
thuật. Em xin cảm ơn thầy/cô và các bạn đã lắng nghe. Em sẵn sàng trả lời câu
hỏi ạ.

---

## Câu hỏi dự kiến (ghi chú chuẩn bị — không phải slide)

- **Vì sao chọn BGE-small mà không phải mô hình embedding lớn hơn?**
  Miễn phí, chạy cục bộ trên CPU, đủ tốt ở quy mô dữ liệu hiện tại. Lộ trình
  có nâng cấp lên bge-m3 (1024 chiều) hoặc Voyage — nhưng *sau khi* có bộ câu
  hỏi vàng đủ lớn để đo được chênh lệch, vì nâng cấp đòi embedding lại toàn
  bộ và migration schema.

- **Vì sao dùng một Postgres thay vì vector database chuyên dụng?**
  Ở quy mô này, hợp nhất kết quả trong một câu SQL thắng việc vận hành và
  đồng bộ kho thứ hai. HNSW của pgvector xử lý thoải mái cỡ một triệu chunk.
  Khi vượt quy mô đó mới cần cân nhắc tách.

- **Làm sao biết trích dẫn đúng?** Chúng được kiểm chứng lại bằng so sánh
  chuỗi chính xác qua phép đối chiếu offset ký tự; tỷ lệ khớp là cổng chặn
  triển khai (≥ 0,90). Đây là kiểm chứng cú pháp — trích đúng chữ; còn "câu
  trả lời có suy diễn đúng từ đoạn trích không" là việc của faithfulness
  trong Ragas.

- **PDF scan (ảnh) thì sao?** Chưa hỗ trợ — chưa có OCR; nằm trong hướng
  phát triển ở mục nguồn dữ liệu.

- **Vì sao hằng số 60 trong RRF?** Giá trị chuẩn từ bài báo RRF gốc
  (Cormack và cộng sự); nó làm mềm chênh lệch giữa các thứ hạng đầu để không
  danh sách nào thống trị. Thực nghiệm cho thấy kết quả không nhạy với giá
  trị này.

- **Chi phí vận hành?** Embedding miễn phí (chạy cục bộ). Sinh câu trả lời
  dùng prompt caching để giảm chi phí phần tiền tố lặp lại. Rerank có hạn mức
  miễn phí lớn và là tùy chọn. Toàn bộ hạ tầng còn lại là mã nguồn mở tự vận
  hành.

- **Prompt injection qua PDF nguy hiểm đến đâu?** Nội dung chunk đi thẳng
  vào prompt, nên một PDF chứa chỉ thị độc hại về lý thuyết có thể lái mô
  hình. Yếu tố giảm nhẹ: system prompt ràng buộc chỉ trả lời từ kết quả tìm
  kiếm, cấu trúc Citations API, và không có công cụ nào để chiếm quyền. Nhưng
  chưa có bộ kiểm thử đối kháng — em xếp nó ở ưu tiên bốn trong hướng phát
  triển.

- **Vì sao không dùng Docling cho parsing cấu trúc?** Docling kéo theo
  PyTorch và mô hình nặng, trái với định hướng CPU-only của dự án. Phát hiện
  đề mục bằng thống kê phông chữ đạt phần lớn lợi ích với chi phí gần bằng
  không; Docling vẫn là phương án nâng cấp cho trích xuất bảng và PDF nhiều
  cột.
