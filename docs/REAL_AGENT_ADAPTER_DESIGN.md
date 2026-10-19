# Minimum gerçek-ajan karşılaştırma adaptörü

Durum: **tasarım; uygulama ve canlı karşılaştırma NOT_RUN.** Öncelik P0 çekirdek
güvenilirliği → küçük gerçek iş tamamlama pilotu → 20 senaryo → gerekirse MCP/Codex
ürün adaptörü → ancak ölçülmüş ihtiyaç varsa SQLite/FTS5. Önceki plandaki manuel
aktarımı P0'dan önce çalıştırma sırası bu kararla değiştirilmiştir.

## Tek hedef

Yarım kalan bir bug fix'e dönen aynı Codex, doğru dosyada doğru düzeltmeyi
tamamlıyor mu? Geçmişte başarısız olmuş yaklaşımı tekrar ediyor mu, önceki testin
neyi kanıtlayıp kanıtlamadığını ayırıyor mu? Birincil çıktı cevap kalitesi değil,
bağımsız kabul testinden geçen son ağaç ve yanlış bağlam kullanımının olmamasıdır.

Adaptör tek Python test sürücüsü olarak tasarlanır; Handoffstone çekirdeğine yeni
sunucu, bağımlılık veya retrieval motoru eklenmez. İlk sürüm bir seferde tek run
çalıştırır, alt ajan veya arka plan servisi yönetmez.

## Üç kol, aynı olaylar

| Kol | Checkpoint yüzeyi | Devam yüzeyi |
| --- | --- | --- |
| A: Codex + AGENTS.md | Normal repo dokümanında güçlü manuel `HANDOFF.md` | Aynı dosyayı okur; Git ve kaynak incelemesi serbest |
| B: Codex + Basic Memory | İzole yerel projede native karar/checkpoint notları | Native orient/read akışı; araç yanıtları kaydedilir |
| C: Codex + Handoffstone | P0 API'siyle kayıt + ContextPackage JSON/wire | Açık cursor'dan Python API ile geri okunan paket |

A kolu bilerek zayıf bir özetle sınırlandırılmaz. Üçüne aynı kaynak olaylar,
başarısız yaklaşım, test receipt'leri, güncel Git durumu ve iş talimatı verilir.
Ürünün kendi başarısızlığı ile ölçüm wrapper'ının sorunu ayrı hata kodları taşır.
Wrapper hiçbir kola eksik karar/kanıt doğrulaması veya gizli otomatik onarım eklemez.

## Bir run'ın yaşam döngüsü

1. **Prepare:** Sabit commit'ten izole checkout hazırla. Bilinen hata, kamuya açık
   testler ve gizli kabul testleri ayrı tutulur. Mümkünse izinli gerçek bir geçmiş
   bug fix küçültülür; sentetik fixture ile tarihsel vaka ayrı etiketlenir.
2. **Start:** Kaynak ajan sorunu araştırır; fixture'ın belirlediği kesilme noktasında
   kalır. Henüz kabulü geçmeyen düzeltme ve başarısız deneme kaydı korunur. Kaynak
   fazının çıktıları hash'lenir; eşlenmiş karşılaştırmada üç kol aynı durumu alır.
3. **Checkpoint:** Aynı talimatla üç kol kendi biçiminde kalıcı kayıt üretir. Dönüş
   ID'si tek başına onay sayılmaz: yeni okuyucu ile aynı checkpoint geri okunur.
4. **Interrupt:** Yalnız test süreci/oturumu sonlandırılır. Kullanıcının Desktop
   uygulaması, canlı işi veya Pi'si kapatılmaz. İlk pilot kontrollü kesilme yapar;
   kayıt ortasında kill ayrı dayanıklılık senaryosudur.
5. **Resume:** Yeni alıcı sohbet aynı iş hedefiyle başlar; önceki sohbet geçmişi
   verilmez. Yalnız kendi kolunun izinli hafızasına ve aynı kaynak ağacına erişir.
   Orkestratör gizli çözümü veya doğru dosyanın yerini fısıldamaz.
6. **Complete:** Ajan kodu değiştirir ve uygun testleri çalıştırır. Son ağaç/diff,
   süreç olayları, hangi bağlamı aldığı ve token usage kaydedilir.
7. **Grade:** Sürücü ajanın “bitti” mesajından bağımsız, kendi kabul testini aynı
   son ağaçta çalıştırır. Doğru son ağaç, davranış, korunmuş ilgisiz iş ve yanlış
   proje bilgisinin kullanılmaması birlikte değerlendirilir.

Kaynak fazının değişkenliğini ölçen ikinci doğal kullanım koşusunda her kol kendi
başlangıç oturumunu üretir. Bu koşu eşlenmiş checkpoint deneyiyle karıştırılmaz;
ilk koşu aktarımı, ikincisi yakalama + devam zincirini ölçer.

## Sürücü ve ince arayüz

Önerilen gelecek dosyalar: `bench_agent.py`, `agent_scenarios/`,
`test_agent_adapter.py`. Bu görevde oluşturulmadılar.

```text
prepare(fixture, arm, run_id) -> workspace + isolated_config
checkpoint(source_artifacts, arm) -> cursor + readback_receipt
retrieve(cursor, task, token_budget, arm) -> context + tool_receipts
run_agent(task, workspace, context) -> events + usage + final_tree
grade(final_tree, hidden_oracle, receipts) -> criterion_results
```

Handoffstone kolunun wrapper'ı yalnız mevcut Python fonksiyonlarını çağırır.
Basic Memory kolu gerçek araç yanıtını kullanır; not içeriği elle taklit edilmez.
A kolu da aynı kaynakları yazabilir. `retrieve` için eksik tokenizer/kurulum veya
checkpoint hatası varsa `BLOCKED`/`FAIL` döner; boş context veya uydurma başarıyla
devam edilmez. Düz metin talimatlarını mekanik güvenlik kapısı saymayız.

## Codex çalıştırma sınırı

OpenAI'nin non-interactive belgeleri `codex exec --json` için JSONL olayları ve
`turn.completed.usage` bilgisi tanımlar. Kurulu CLI bu çalışmada `0.162.1` olarak
görüldü; `--json`, `--output-last-message`, `--model`, `--sandbox`, `--cd` ve stdin
girdisi yardım çıktısında kontrol edildi. Bir ajan çalıştırılmadı.
[Resmi kaynak](https://learn.chatgpt.com/docs/non-interactive-mode).

Gelecekte sürücü `subprocess` argv listesi ve stdin kullanır; shell komut
birleştirmesi yapmaz. Her kol aynı sabit model/effort/build ve `workspace-write`
izniyle çalışır. Yeni alıcı sohbet açılır; `resume --last` ile yanlış sohbete
bağlanılmaz. Gerekli onay yüzünden koşu durursa bu görünür engeldir; sandbox veya
hook güveni atlanmaz.

Testlere özel yapılandırma ve memory kökleri gerekir. Kullanıcının kişisel memory,
global eklenti/hook'ları ve üretim projeleri üç kola karışmamalı. Kimlik doğrulama
kurulmadan koşu `BLOCKED` kalır; anahtarlar fixture/config/log içine kopyalanmaz.
Gerçek host özelliklerini desteklemeyen CLI koşusu Desktop hook başarısı sayılmaz.

## Ölçüm

| Ölçüt | Hesap |
| --- | --- |
| Gerçek tamamlama | Bağımsız kabulün geçtiği son ağaç / çalıştırılan run; BLOCKED ve NOT_RUN sayıları ayrıca |
| Doğru devam | Doğru cursor, dosya/iş durumu, kabulü geçen sonraki eylem |
| Başarısız yaklaşımı tekrar | Fixture'daki eski yanlış yaklaşımın yeni kanıt olmadan tekrarı; diff/komut kayıtları ve kör rubrik |
| Test kapsamını doğru yorumlama | Önceki test receipt'iyle sınırlı iddia; koşulmamış testi geçti sayma ayrı hata |
| Yanlış bağlam | Başka repo/branch bilgisiyle yanlış eylem; retrieval sızıntısı ve eylemde kullanım ayrı |
| Süre | Resume isteğinden bağımsız kabul sonuna kadar monotonic süre; retrieval dahil, checkpoint süresi ayrıca |
| Model tüketimi | Kaynak, checkpoint ve resume fazları için ayrı input/cached/output kullanım; eksik alan bilinmiyor |
| Maliyet | Deney tarihindeki sabit fiyat anlık görüntüsü ve gerçekleşen kullanım; cached input iki defa sayılmaz |
| Hafıza bütçesi | İlk paket ve sonraki bütün memory yanıtları, gerçek tokenizer ile; toplam model input'undan ayrı |

Fiyat veya usage yoksa maliyet `NOT_RUN`/bilinmiyor, sıfır değil. `len//4` gerçek
token diye yazılmaz. Her gizli kabul testinin exit kodu ve stdout/stderr özeti
ayrı receipt'tir; ajan veya sürücü exit 0 tek başına iş başarısı değildir.

## Küçük pilot ve 20 senaryoya geçiş

İlk pilot üç vakayı kapsar: yarım bug fix + eski başarısız yaklaşım (S08/S09),
branch değişiminden sonra eski checkpoint (S05/S06), yazma hatası/bozuk tail (S13).
Üç kol ve iki tekrar: **18 planlı run**. İlk iki vaka gerçekten kod tamamlatır;
üçüncü vaka yanlış devam etmekten kaçınmayı ölçer. Bunlar henüz çalıştırılmadı.

Önce negatif kontrol: yanlış branch notu, sahte test PASS'ı veya bozuk tail,
değerlendirme sonucunu bozmalı. Sonra bir run'ın kaynak → checkpoint → yeni
sohbet → bağımsız kabul delilleri eksiksiz olmalı. Sürücü kanıtının doğruluğu
görülmeden 300 koşuya geçilmez. Pilot iyileştirmeleri dondurulduktan sonra
20 senaryo × 3 kol × 5 tekrar uygulanır; holdout oracle'lar değerlendirme
uyarlamasından ayrı tutulur. Önceki planda “5 holdout” yanında dört ID vardı;
nihai set S05, S07, S12, S17, S18 olarak sabitlenir.

Temel eşikler önceki planla korunur: en az %90 güncel karar/gerekçe, ilgili devam
altkümesinde en az %95, gözlenen yanlış proje sızıntısı ve kanıtsız VERIFIED sıfır,
memory context bütçesi en fazla 1.500 gerçek token. Tekrarlar az olduğu için ham
sayı ve güven aralığı verilir; pilot ticari/istatistiksel üstünlük kanıtı değildir.

Yatırım kararı gerçek iş tamamlama, güvenilirlik ve süre/maliyet farkına dayanır.
Basic Memory'ye göre anlamlı kazanım yoksa genel hafıza servisine genişlemek
yerine taşınabilir handoff kütüphanesi konumlandırması korunur.
