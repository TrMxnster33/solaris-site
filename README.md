# Solaris

Sarı-beyaz temalı, e-posta doğrulaması, oturum açma, onaylı ziyaretçi analitiği ve admin paneli bulunan Solaris web sitesi. Backend Python standart kütüphanesi ve SQLite kullanır; ayrıca paket kurmanız gerekmez.

## Gereksinimler

- Python 3.9 veya üzeri
- E-posta doğrulama kodu göndermek için SMTP erişimi

## İlk çalıştırma

1. `.env.example` dosyasının bir kopyasını `.env` adıyla oluşturun.
2. E-posta sağlayıcınızın SMTP sunucusu, kullanıcı adı ve parola bilgilerini `.env` dosyasına yazın. `SMTP_FROM` değerini bu posta hesabına göre ayarlayın.
3. Solaris klasöründe terminal açıp `python server.py` komutunu çalıştırın.
4. Tarayıcıda `http://127.0.0.1:8000` adresini açın.

İlk çalıştırmada `.env` içindeki `ADMIN_EMAIL` ve `ADMIN_PASSWORD` değerleriyle admin hesabı oluşturulur. E-posta varsayılanı `eymenefeyt3@gmail.com` olarak ayarlanmıştır; parolayı `.env` dosyasında kendiniz belirleyin ve kaynak koduna eklemeyin. Admin ilk girişinde parolasını değiştirmek zorundadır. Bu hesap yalnızca ilk oluşturma sırasında eklenir; `.env` değerini sonradan değiştirmek veritabanındaki parolayı değiştirmez. Gerekirse parola değiştirme ekranını kullanın.

Yönetim paneli uygulama çalışırken `/admin` adresindedir ve yalnızca oturum açmış, başlangıç parolasını değiştirmiş bir admin hesabıyla kullanılabilir. Panel API'si de her istekte rolü ve oturumu sunucu tarafında denetler; URL'yi bilmek yetki vermez.

## E-posta doğrulaması

Kayıt sırasında verilen adrese altı haneli, 10 dakika geçerli bir kod gönderilir. Kodun tahmin edilmesini zorlaştırmak için deneme sayısı sınırlandırılır; yeni kod isteği 60 saniyede bir yapılabilir. Doğrulama, e-posta adresinin biçimini kontrol etmekten fazlasını yapar: posta kutusuna erişimi kanıtlar. Harici bir sağlayıcı olmadan bir e-posta adresinin var olup olmadığı kesin biçimde sorgulanamaz.

SMTP bilgileri yapılandırılmamışsa kayıt isteği açık hata verir; e-posta doğrulaması atlanmaz.

## Ziyaretçi analitiği ve gizlilik

Ziyaretçi analitiği varsayılan olarak kapalıdır. Ziyaretçiye gösterilen bilgilendirme alanından açıkça kabul edilmeden sayfa ziyareti veya IP adresi kaydedilmez. Kabul edilirse sayfa yolu, IP adresi, cihaz sınıfı (mobil/tablet/masaüstü) ve zaman bilgisi SQLite'a yazılır. Onay reddedilebilir; daha önce kabul edilmiş analitik izni geri çekildiğinde o ziyaretçinin analitik kayıtları silinir. Bir yıllık, rastgele ziyaretçi çerezi HttpOnly/SameSite olarak ayarlanır; hesap çereziyle ilişkilendirilmez. Ziyaret verileri varsayılan olarak 90 gün sonra silinir (`ANALYTICS_RETENTION_DAYS`).

Yönetici paneli anlık (son beş dakikadaki), tekil ve sayfa görüntüleme sayılarını; son 200 sayfa ziyaretini ve doğrulanmış e-posta adreslerini gösterir. Admin API erişimi sunucuda yetkilendirilir. `TRUSTED_PROXIES` ayarı yalnızca ters vekilinizin güvenilir IP/CIDR değerlerini içeriyorsa sunucu, vekilin `X-Forwarded-For` zincirinden gerçek ziyaretçi IP'sini alır. Vekil bu başlığı güvenli şekilde ayarlamalıdır; aksi halde uygulama doğrudan TCP bağlantısının IP adresini kaydeder.

Panel parola/oturum ile korunur; iletim sırasında şifreleme için üretimde HTTPS ve `COOKIE_SECURE=true` zorunludur. SQLite veritabanı kendi başına disk üzerinde şifrelenmez; dosya erişimini kısıtlayın ve disk/volume şifrelemesi kullanın. IP adresleri kişisel veridir: üretim öncesi gizlilik bildiriminizi, yasal dayanağı, saklama süresini ve veri sahibi taleplerini kendi hukukî yükümlülüklerinize göre belirleyin.

## Sunucuya dağıtım

Üretimde `HOST=127.0.0.1` ile uygulamayı yerel arayüzde çalıştırın ve HTTPS sağlayan Nginx/Caddy gibi bir ters vekil arkasından yayınlayın. HTTPS etkinleştirildikten sonra `.env` içinde `COOKIE_SECURE=true` ayarlayın. `ADMIN_PASSWORD` değerini dağıtımdan önce güçlü ve benzersiz bir parolayla değiştirin. `solaris.db` dosyası kullanıcı hesaplarını ve oturumları içerir; herkese açık statik dizinden ayrı, yedeklenen ve erişimi kısıtlı bir yerde saklamak için `SOLARIS_DB` ayarlayabilirsiniz.

Hesap parolaları PBKDF2-HMAC-SHA256 ile salt kullanılarak saklanır; oturum çerezleri HttpOnly ve SameSite=Lax olarak ayarlanır.
