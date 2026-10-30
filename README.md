# Solaris

Solaris, topluluk ve Minecraft dünyası için web portalıdır. Web kullanıcı hesapları yerel SQLite veritabanında tutulur; hesap parolaları PBKDF2-HMAC-SHA256 ile hash'lenir. Uygulama MySQL/AuthMe'ye bağlanmaz ve oyun hesabı parolalarını kullanmaz.

## Gereksinimler ve ilk çalıştırma

- Python 3.9 veya üzeri; ek paket gerekmez.
- `.env.example` dosyasını `.env` olarak kopyalayın.
- Admin hesabı `.env` içindeki `ADMIN_EMAIL`, `ADMIN_USERNAME` ve `ADMIN_PASSWORD` ayarlarıyla SQLite'a eklenir/güncellenir. Giriş ekranında admin kullanıcı adı veya e-posta adresi kullanılabilir. Admin kullanıcı adı varsayılanı `babakutletenv4` şeklindedir. Canlı sunucuda güçlü, benzersiz bir admin parolası kullanın.
- Terminalden `python server.py` çalıştırın. Sunucu varsayılan olarak `0.0.0.0:8000` üzerinde dinler; yerel tarayıcıdan `http://127.0.0.1:8000` adresini açın.

`solaris.db` varsayılan olarak proje klasöründe oluşturulur. `SOLARIS_DB` ile veritabanını web statik dosyalarının dışında, erişimi kısıtlı bir dizine taşıyabilirsiniz. Üretimde HTTPS arkasında yayınlayın ve `.env` içinde `COOKIE_SECURE=true` ayarlayın.

## Web hesabı

Kayıt formu e-posta, oyuncu adı, parola ve parola tekrarını alır. Oyuncu adı 3-16 karakterlik harf/rakam/alt çizgi biçimindedir; parola 10-128 karakter olmalıdır. Kayıt anında hesap açılır ve kullanıcı oturum açmış olur. E-posta OTP/aktivasyonu yoktur; e-posta biçimi kontrol edilir ancak posta kutusunun varlığı veya sahipliği kanıtlanmaz.

Giriş hem e-posta hem oyuncu adı ile yapılabilir. “Beni hatırla” seçeneği oturumu 30 gün sürdürür; seçilmezse tarayıcı oturumu ve sunucudaki 24 saatlik süre kullanılır. Oturum çerezi HttpOnly ve SameSite=Lax olarak ayarlanır.

Web parolası Minecraft/AuthMe parolasından ayrıdır. Eski veritabanındaki yalnızca geçerli e-posta/oyuncu adı ve tanınabilir PBKDF2 hash'i bulunan kullanıcılar yeni şemaya taşınır. `@minecraft.local` hesapları ve SHA-256 oyun hash'leri taşınmaz; eski oturumlar şema değişiminde geçersiz kılınır. Önceden SQLite dosyasının yedeğini alın.

## Yönetici paneli

Admin olarak giriş yaptıktan sonra hesap bölümündeki yönetim panelinde son beş dakikadaki aktif ziyaretçi sayısı, tekil ziyaretçiler, sayfa görüntülemeleri, analitik izni veren ziyaretçilerin IP/cihaz/kaynak/tarayıcı/dil/tarih bilgileri ve tüm kayıtlı hesaplar görünür. Büyük listeler 50 kayıtlık sayfalara bölünür. Hesap parolaları ve parola hash'leri panel API'sinin çıktısına dahil edilmez. `/admin` adresi ana sayfaya yönlenir; gerçek yetkilendirme her API isteğinde sunucu tarafında yapılır.

Admin hesabı `ADMIN_PASSWORD` ayarlanmadan otomatik oluşturulmaz. Bu parola her uygulama başlangıcında yapılandırılmış admin hesabının parolasını belirler; değişiklikte `.env` değerini güncelleyip uygulamayı yeniden başlatın. Gizli değeri kaynak koduna veya paylaşılan ortama koymayın.

## Analitik ve gizlilik

Analitik varsayılan olarak kapalıdır. Ziyaretçinin açıkça kabul etmesinden sonra IP adresi, site içi sayfa, cihaz sınıfı, tarayıcı/user-agent, dil, yönlendiren sitenin alan adı ve zaman bilgisi SQLite'a yazılır. Onay reddedilebilir veya Gizlilik tercihleri ile geri alınabilir; geri alma o ziyaretçinin analitik kayıtlarını ve ziyaretçi çerezini siler. Kayıtlar varsayılan olarak 90 gün sonra silinir (`ANALYTICS_RETENTION_DAYS`).

Panelde coğrafi konum gösterilmez; IP'den şehir/ülke bilgisi çıkarımı yapılmaz ve IP üçüncü taraf servislere gönderilmez. Proxy arkasında gerçek IP almak için yalnızca güvenilir proxy adreslerini `TRUSTED_PROXIES` içinde tanımlayın ve proxy'nin `X-Forwarded-For` başlığını güvenli şekilde ayarladığından emin olun. IP adresleri kişisel veridir; yayın öncesi gizlilik bildirimi, saklama süresi ve yasal yükümlülükleri ayrıca değerlendirin. SQLite dosyası disk üzerinde kendiliğinden şifrelenmez; erişimi kısıtlayın ve disk/volume şifrelemesi kullanın.

## Minecraft bağlantısı

Minecraft sunucu adresini `MINECRAFT_ADDRESS` ve sürümü `MINECRAFT_VERSION` üzerinden yayınlayabilirsiniz. Bu uygulama oyun sunucusu hesaplarını doğrulamaz; web formuna Minecraft parolası yazılmamalıdır.
