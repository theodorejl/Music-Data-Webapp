"""The tree of genres: main genres, their sub-genres, and under them the 6,291 genres of Every
Noise at Once (the sub-sub-genres), laid out as an atlas.

1. Classification. Each genre of the map is read by its name, the way genre names are built: the
   head comes last ("deep house" is house, "pop punk" is punk, "dance pop" is pop), a few words
   decide on their own wherever they are (cumbia, sertanejo, worship…), and a place before the
   head makes a regional scene ("swedish indie", "rap marseille"). The rules below are tried in
   order; a genre no rule recognises (an Every Noise coinage such as "escape room") takes the
   sub-genre most common among its nearest neighbours by sound.

2. Layout. The atlas keeps Every Noise's logic at large scale (electronic and mechanical at the
   top, organic at the bottom, dense on the left, spiky on the right) but gathers each family in
   one place: every main genre gets a contiguous territory sized to its number of genres, seeded
   where its genres sit on Every Noise; inside it, each sub-genre gets its own district the same
   way; inside that, every genre gets an equal share. Territories are cut from a fine grid of
   points with a capacity-constrained power diagram (balanced "Voronoi treemap"), so borders are
   organic and nothing overlaps. The result is stored in app/assets/genre_tree.json by
   `python -m scripts.build_genre_map --tree`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np

ASSET = Path(__file__).resolve().parents[1] / "app" / "assets" / "genre_tree.json"
ASPECT = 1.6  # the atlas is drawn 1.6 times wider than tall

# --- the tree ----------------------------------------------------------------------------------------------
# main genre: (French, English)
MAIN = {
    "electronic": ("Électronique", "Electronic"), "pop": ("Pop", "Pop"), "indie": ("Indie & alternatif", "Indie & alternative"),
    "rock": ("Rock", "Rock"), "metal": ("Metal", "Metal"), "punk": ("Punk & hardcore", "Punk & hardcore"),
    "hiphop": ("Hip-hop & rap", "Hip hop & rap"), "rnb": ("R&B, soul & funk", "R&B, soul & funk"), "jazz": ("Jazz", "Jazz"),
    "blues": ("Blues", "Blues"), "country": ("Country & americana", "Country & americana"),
    "folk": ("Folk & auteurs", "Folk & songwriters"), "latin": ("Latino", "Latin"), "brazil": ("Brésil", "Brazil"),
    "caribbean": ("Reggae & Caraïbes", "Reggae & Caribbean"), "africa": ("Afrique", "Africa"),
    "world": ("Musiques du monde", "World & traditional"), "classical": ("Classique", "Classical"),
    "screen": ("Films, jeux & scène", "Film, games & stage"), "sacred": ("Gospel & sacré", "Gospel & sacred"),
    "experimental": ("Expérimental", "Experimental"), "other": ("Autres sons", "Other sounds"),
}
# sub-genre: (main genre, French, English)
SUB = {
    # electronic
    "house": ("electronic", "House", "House"), "techno": ("electronic", "Techno", "Techno"),
    "trance": ("electronic", "Trance", "Trance"), "dnb": ("electronic", "Drum & bass, jungle", "Drum & bass, jungle"),
    "bass": ("electronic", "Dubstep & bass", "Dubstep & bass"), "breaks": ("electronic", "Breakbeat & UK garage", "Breakbeat & UK garage"),
    "hard": ("electronic", "Hardstyle & hardcore", "Hardstyle & hardcore"), "edm": ("electronic", "EDM & dance", "EDM & dance"),
    "disco": ("electronic", "Disco & nu-disco", "Disco & nu-disco"), "ambient": ("electronic", "Ambient", "Ambient"),
    "downtempo": ("electronic", "Downtempo, trip hop & lo-fi", "Downtempo, trip hop & lo-fi"),
    "electronica": ("electronic", "Electronica & IDM", "Electronica & IDM"), "synth": ("electronic", "Synthwave & electro", "Synthwave & electro"),
    "industrial": ("electronic", "Industriel & EBM", "Industrial & EBM"), "elscenes": ("electronic", "Scènes électroniques", "Electronic scenes"),
    # pop
    "dancepop": ("pop", "Dance pop & tubes", "Dance pop & hits"), "synthpop": ("pop", "Synthpop & électropop", "Synthpop & electropop"),
    "artpop": ("pop", "Art pop", "Art pop"), "softpop": ("pop", "Pop douce & adulte", "Soft & adult pop"),
    "asianpop": ("pop", "K-pop, J-pop & pop d'Asie", "K-pop, J-pop & Asian pop"), "chanson": ("pop", "Chanson & variété", "Chanson & variety"),
    "worldpop": ("pop", "Pop du monde", "Pop around the world"),
    # indie
    "indierock": ("indie", "Indie rock", "Indie rock"), "indiepop": ("indie", "Indie pop & dream pop", "Indie & dream pop"),
    "shoegaze": ("indie", "Shoegaze & slowcore", "Shoegaze & slowcore"), "indietronica": ("indie", "Indie électronique", "Indie electronic"),
    "alternative": ("indie", "Alternatif", "Alternative"), "lofi": ("indie", "Lo-fi & bedroom", "Lo-fi & bedroom"),
    "indiescenes": ("indie", "Scènes indie", "Indie scenes"),
    # rock
    "classicrock": ("rock", "Rock classique", "Classic rock"), "hardrock": ("rock", "Hard rock & glam", "Hard rock & glam"),
    "psych": ("rock", "Psyché & garage", "Psych & garage"), "prog": ("rock", "Prog & art rock", "Prog & art rock"),
    "postrock": ("rock", "Post-rock & math rock", "Post-rock & math rock"), "postpunk": ("rock", "Post-punk, new wave & goth", "Post-punk, new wave & goth"),
    "altrock": ("rock", "Rock alternatif & grunge", "Alternative rock & grunge"), "rocknroll": ("rock", "Rock'n'roll & rockabilly", "Rock'n'roll & rockabilly"),
    "poprock": ("rock", "Pop rock & power pop", "Pop rock & power pop"), "rockscenes": ("rock", "Rock du monde", "Rock around the world"),
    # metal
    "heavy": ("metal", "Heavy & speed metal", "Heavy & speed metal"), "thrash": ("metal", "Thrash & groove", "Thrash & groove"),
    "death": ("metal", "Death metal", "Death metal"), "black": ("metal", "Black metal", "Black metal"),
    "doom": ("metal", "Doom, sludge & stoner", "Doom, sludge & stoner"), "metalcore": ("metal", "Metalcore & deathcore", "Metalcore & deathcore"),
    "numetal": ("metal", "Nu metal & metal alternatif", "Nu & alternative metal"), "power": ("metal", "Power, symphonique & gothique", "Power, symphonic & gothic"),
    "progmetal": ("metal", "Metal progressif & djent", "Progressive metal & djent"), "grind": ("metal", "Grindcore & extrême", "Grindcore & extreme"),
    "folkmetal": ("metal", "Folk & pagan metal", "Folk & pagan metal"), "metalscenes": ("metal", "Metal du monde", "Metal around the world"),
    # punk
    "punkrock": ("punk", "Punk rock & oi!", "Punk rock & oi!"), "hardcore": ("punk", "Hardcore punk", "Hardcore punk"),
    "poppunk": ("punk", "Pop punk & emo", "Pop punk & emo"), "posthardcore": ("punk", "Post-hardcore & screamo", "Post-hardcore & screamo"),
    "skapunk": ("punk", "Ska punk", "Ska punk"), "garagepunk": ("punk", "Garage punk & psychobilly", "Garage punk & psychobilly"),
    "punkscenes": ("punk", "Punk du monde", "Punk around the world"),
    # hip hop
    "trap": ("hiphop", "Trap", "Trap"), "drill": ("hiphop", "Drill", "Drill"), "boombap": ("hiphop", "Boom bap & old school", "Boom bap & old school"),
    "althiphop": ("hiphop", "Hip-hop alternatif & underground", "Alternative & underground hip hop"),
    "south": ("hiphop", "Sud & côte Ouest", "South & West Coast"), "cloud": ("hiphop", "Cloud rap, emo rap & phonk", "Cloud rap, emo rap & phonk"),
    "poprap": ("hiphop", "Pop rap & rap mélodique", "Pop rap & melodic rap"), "uk": ("hiphop", "Grime & rap UK", "Grime & UK rap"),
    "frenchrap": ("hiphop", "Rap francophone", "French-language rap"), "rapscenes": ("hiphop", "Rap du monde", "Rap around the world"),
    # r&b
    "rnbnow": ("rnb", "R&B contemporain", "Contemporary R&B"), "neosoul": ("rnb", "Neo soul & R&B alternatif", "Neo soul & alternative R&B"),
    "soul": ("rnb", "Soul classique", "Classic soul"), "funk": ("rnb", "Funk & boogie", "Funk & boogie"),
    "slow": ("rnb", "New jack swing & quiet storm", "New jack swing & quiet storm"), "doowop": ("rnb", "Doo-wop & groupes vocaux", "Doo-wop & vocal groups"),
    "rnbscenes": ("rnb", "R&B du monde", "R&B around the world"),
    # jazz
    "bop": ("jazz", "Bebop & hard bop", "Bebop & hard bop"), "cool": ("jazz", "Cool & modal", "Cool & modal"),
    "free": ("jazz", "Free & spiritual jazz", "Free & spiritual jazz"), "fusion": ("jazz", "Fusion, jazz-funk & nu jazz", "Fusion, jazz-funk & nu jazz"),
    "vocaljazz": ("jazz", "Jazz vocal & standards", "Vocal jazz & standards"), "swing": ("jazz", "Swing, big band & manouche", "Swing, big band & gypsy jazz"),
    "latinjazz": ("jazz", "Jazz latin", "Latin jazz"), "modernjazz": ("jazz", "Jazz contemporain & instrumental", "Contemporary & instrumental jazz"),
    "smooth": ("jazz", "Smooth jazz", "Smooth jazz"), "jazzscenes": ("jazz", "Jazz du monde", "Jazz around the world"),
    # blues
    "delta": ("blues", "Blues acoustique & delta", "Acoustic & delta blues"), "electricblues": ("blues", "Blues électrique & Chicago", "Electric & Chicago blues"),
    "bluesrock": ("blues", "Blues rock", "Blues rock"), "soulblues": ("blues", "Soul blues & swamp", "Soul blues & swamp"),
    # country
    "classiccountry": ("country", "Country classique", "Classic country"), "moderncountry": ("country", "Country moderne", "Modern country"),
    "americana": ("country", "Americana & alt-country", "Americana & alt-country"), "bluegrass": ("country", "Bluegrass & old-time", "Bluegrass & old-time"),
    "countryscenes": ("country", "Country du monde", "Country around the world"),
    # folk
    "songwriter": ("folk", "Auteurs-compositeurs", "Singer-songwriters"), "indiefolk": ("folk", "Indie folk", "Indie folk"),
    "folkrevival": ("folk", "Folk traditionnel & revival", "Traditional folk & revival"), "celtic": ("folk", "Celtique", "Celtic"),
    "folkscenes": ("folk", "Folk du monde", "Folk around the world"),
    # latin
    "urbano": ("latin", "Reggaeton & urbano", "Reggaeton & urbano"), "latinpop": ("latin", "Pop latino & ballades", "Latin pop & ballads"),
    "salsa": ("latin", "Salsa & tropical", "Salsa & tropical"), "cumbia": ("latin", "Cumbia & vallenato", "Cumbia & vallenato"),
    "bachata": ("latin", "Bachata & merengue", "Bachata & merengue"), "mexico": ("latin", "Musique mexicaine", "Regional Mexican"),
    "latinrock": ("latin", "Rock & indie latino", "Latin rock & indie"), "andes": ("latin", "Folklore andin & sud-américain", "Andean & South American folk"),
    "tango": ("latin", "Tango", "Tango"), "latinscenes": ("latin", "Scènes latines", "Latin scenes"),
    # brazil
    "mpb": ("brazil", "MPB & bossa nova", "MPB & bossa nova"), "samba": ("brazil", "Samba & pagode", "Samba & pagode"),
    "sertanejo": ("brazil", "Sertanejo", "Sertanejo"), "nordeste": ("brazil", "Forró, axé & brega", "Forró, axé & brega"),
    "funkbr": ("brazil", "Funk brésilien", "Brazilian funk"), "brscenes": ("brazil", "Rock, rap & indie brésiliens", "Brazilian rock, rap & indie"),
    # caribbean
    "reggae": ("caribbean", "Reggae roots & dub", "Roots reggae & dub"), "dancehall": ("caribbean", "Dancehall", "Dancehall"),
    "ska": ("caribbean", "Ska & rocksteady", "Ska & rocksteady"), "soca": ("caribbean", "Soca & calypso", "Soca & calypso"),
    "zouk": ("caribbean", "Zouk, kompa & kizomba", "Zouk, kompa & kizomba"), "reggaescenes": ("caribbean", "Reggae du monde", "Reggae around the world"),
    # africa
    "afrobeats": ("africa", "Afrobeats & afropop", "Afrobeats & afropop"), "afrobeat": ("africa", "Afrobeat & highlife", "Afrobeat & highlife"),
    "amapiano": ("africa", "Amapiano, gqom & kwaito", "Amapiano, gqom & kwaito"), "rumba": ("africa", "Rumba, soukous & makossa", "Rumba, soukous & makossa"),
    "westafrica": ("africa", "Afrique de l'Ouest & mandingue", "West Africa & Mande"), "eastafrica": ("africa", "Afrique de l'Est & éthio-jazz", "East Africa & Ethio-jazz"),
    "africascenes": ("africa", "Scènes africaines", "African scenes"),
    # world
    "eastasia": ("world", "Asie de l'Est", "East Asia"), "southasia": ("world", "Inde & Asie du Sud", "India & South Asia"),
    "seasia": ("world", "Asie du Sud-Est", "Southeast Asia"), "mideast": ("world", "Moyen-Orient & Maghreb", "Middle East & North Africa"),
    "europe": ("world", "Traditions d'Europe", "European traditions"), "balkans": ("world", "Balkans & Europe de l'Est", "Balkans & Eastern Europe"),
    "oceania": ("world", "Océanie & peuples autochtones", "Oceania & indigenous"), "central": ("world", "Asie centrale & Caucase", "Central Asia & Caucasus"),
    # classical
    "early": ("classical", "Médiéval, Renaissance & baroque", "Medieval, Renaissance & Baroque"),
    "romantic": ("classical", "Classique & romantique", "Classical & Romantic era"), "contemporary": ("classical", "Contemporain & minimaliste", "Contemporary & minimalist"),
    "opera": ("classical", "Opéra & lied", "Opera & art song"), "orchestral": ("classical", "Orchestre & musique de chambre", "Orchestral & chamber"),
    "solo": ("classical", "Instruments solistes", "Solo instruments"), "neoclassical": ("classical", "Néo-classique", "Neoclassical"),
    "choral": ("classical", "Chœurs", "Choral"), "classicalscenes": ("classical", "Classique du monde", "Classical around the world"),
    # screen
    "score": ("screen", "Musiques de films", "Film scores"), "games": ("screen", "Jeux vidéo & chiptune", "Video games & chiptune"),
    "anime": ("screen", "Anime & vocaloid", "Anime & vocaloid"), "stage": ("screen", "Comédies musicales & cabaret", "Musicals & cabaret"),
    "tv": ("screen", "Télé, bandes-annonces & library", "TV, trailers & library"),
    # sacred
    "worship": ("sacred", "Louange & pop chrétienne", "Worship & CCM"), "gospel": ("sacred", "Gospel", "Gospel"),
    "chant": ("sacred", "Chants sacrés & dévotion", "Sacred chant & devotional"),
    # experimental
    "noise": ("experimental", "Noise", "Noise"), "drone": ("experimental", "Drone & microsound", "Drone & microsound"),
    "soundart": ("experimental", "Art sonore & musique concrète", "Sound art & musique concrète"),
    "improv": ("experimental", "Improvisation libre", "Free improvisation"), "avant": ("experimental", "Avant-garde", "Avant-garde"),
    # other
    "kids": ("other", "Enfants", "Children"), "spoken": ("other", "Humour & spoken word", "Comedy & spoken word"),
    "wellness": ("other", "Relaxation, sommeil & nature", "Relaxation, sleep & nature"),
    "occasions": ("other", "Fêtes, reprises & karaoké", "Seasonal, covers & karaoke"), "band": ("other", "Fanfares & musiques militaires", "Marching & military bands"),
}

# 1. Words that decide wherever they are in the name: (sub-genre, pattern), the first that matches wins.
RULES: list[tuple[str, str]] = [
    ("kids", r"children|\bkids\b|lullab|nursery|kindermusik|bambini|ninos|infantil|enfants|kinder|barnmusik|barnsagor|"
             r"barnemusikk|kinderen|dong-yo|cartoon|music box|\bvbs\b|crianca|kinderlied|dla dzieci|detskie|chinderlieder|comptine|anak-anak|kodomo|lapsille|bornesang|dzieciecy|\bbajki|\beventyr"),
    ("wellness", r"sleep|meditation|relaxation|relaxative|binaural|healing|white noise|\bspa\b|yoga|focus|study beats|"
                 r"environmental|nature sounds|\brain\b|\bocean\b|asmr|brainwave|reiki|solfeggio|sound bath|singing bowl|"
                 r"new age|calming|massage|mindfulness|shamanic|high vibe|\b8d\b|water sounds|workout|\d+hz|brain waves|kundalini|handpan|\bzen\b|\bnu age\b"),
    ("spoken", r"comedy|comic|stand-up|poetry|spoken word|audiobook|reading|podcast|\bstory|storytelling|sketch|parody|"
               r"novelty|motivation|speech|radio drama|kabarett|humor|humour|cantastorie|slam poetry|hoerspiel|"
               r"horspiel|writing|lustrum|\blesen\b"),
    ("occasions", r"christmas|navidad|\bnoel\b|weihnacht|halloween|karaoke|\bcover|tribute|wedding|birthday|backing track|"
                  r"background music|musica de fondo|muzak|football|fotboll|national anthem|oktoberfest|carnaval|"
                  r"karneval|kermis|cheerleading|drinking song|apres-ski|wrestling|talentschau|concurso de talentos|"
                  r"talent show|previa|stadium anthem|gymcore|\btheme\b|\bbgm\b|mashup|fussball|talentkonkurranse|villancicos|\bremix\b(?! turkce)"),
    ("band", r"marching|military|brass band|fanfare|drum corps|drumline|banda de musica|blasmusik|pipe band|concert band|"
             r"wind band|harmonie|double drumming"),
    ("anime", r"anime|vocaloid|otacore|j-idol|touhou|doujin|seiyu|utaite|nightcore|shonen|shojo|seinen|yaoi|\bmecha\b"),
    ("games", r"video game|\bvgm\b|game music|chiptune|8-bit|bitpop|16-bit|game mood|gaming|nintendocore|rhythm game|\bpixel\b|speedrun"),
    ("score", r"soundtrack|film score|movie|cinematic|hollywood|scorecore|epicore|fantasy|middle earth"),
    ("stage", r"show tunes|broadway|musical|west end|cabaret|operetta|vaudeville|music hall|\brevue|theatre|theater|ballet"),
    ("tv", r"\btv\b|television|trailer|library music|production music|jingle|advertising"),
    ("worship", r"worship|\bccm\b|praise|louvor|adoracion|adoracao|alabanza|cristian|cristao|chretien|christelijk|\blds\b|"
                r"church|catholic|liturg|hymn|kirchen|anbetung|jesus|pentecostal|christian(?! (?:metal|metalcore|"
                r"deathcore|punk|hardcore|hip hop|rap|death|black|thrash|doom|power|symphonic|alternative|rock|indie|"
                r"electronic|edm|trap|drill|emo))|adventista|hinos|crista reformada|rosary|umbanda"),
    ("gospel", r"gospel|negro spiritual|spirituals\b"),
    ("chant", r"\bchant\b|gregorian|sacred|devotional|kirtan|bhajan|mantra|qawwali|\bsufi\b|nasheed|islamic|quran|"
              r"byzantine|orthodox chant|jewish|cantor|piyyut|buddhist|hindu|shabad|gurbani|\bazan\b|madih|\bilahi|"
              r"sholawat|hare krishna|\bzikr|dhikr|zikir|nasyid|\bnaat\b|mappila"),
    # Brazil, Latin America, the Caribbean, Africa: words that are a scene on their own
    ("funkbr", r"^funk\s(?!rock|metal|pop rock|soul)|baile funk|funk carioca|funk paulista|funk mtg|brazilian funk|"
               r"funk ostentacao|funk rj|funk mandelao|rave funk|funk bh|funk consciente|funk das antigas|funk melody|"
               r"tamborzao|mega funk|\bfvnk|rimex"),
    ("sertanejo", r"sertanejo|arrocha|modao|moda de viola|caipira|agronejo|sofrencia|piseiro|pisadinha"),
    ("nordeste", r"forro|\bxote|baiao|\baxe\b|frevo|brega|calypso brasileiro|swingueira|pagodao|aboio|vaquejada|"
                 r"lambada|carimbo|bandinhas|guitarrada|maracatu|\bcoco\b|ciranda|xaxado"),
    ("samba", r"samba|pagode|\bchoro\b|partido alto|chorinho|gafieira|batucada|marchinha|velha guarda"),
    ("mpb", r"\bmpb\b|bossa nova|tropicalia|musica popular brasileira|clube da esquina|vanguarda paulista|violao|"
            r"brazilian jazz|jazz brasileiro"),
    ("brscenes", r"brasileir|brazilian|brasil|gaucha|gaucho|rap nacional|carioca|paulista|mineiro|baiano|capixaba|"
                 r"pernambuc|cearense|goiano|paraense|nordestino|potiguar|jovem guarda|piauiense|maranhense|"
                 r"amazonense|catarinense|paranaense|alagoano|sergipano|tocantinense|brasiliense|manguebeat|musica (?:alagoana|popular mineira|juiz-forana|baiana|feirense)|vaqueiro"),
    ("urbano", r"reggaeton|urbano latino|trap latino|latin trap|latin hip hop|perreo|dembow|neoperreo|\brkt\b|cubaton|"
               r"latin drill|corridos tumbados|reparto|moombahton|trap (?:argentino|chileno|colombiano|peruano|mexicano|"
               r"venezolano|dominicano|boricua|espanol|uruguayo|paraguayo|ecuatoriano|boliviano|cubano)|"
               r"rap (?:dominicano|colombiano|argentino|chileno|mexicano|peruano|venezolano|boricua|espanol|cubano|"
               r"ecuatoriano|uruguayo|boliviano|paraguayo|latino|conciencia|guatemalteco|hondureno|salvadoreno|"
               r"costarricense|panameno|nicaraguense|canario|andaluz|gallego|catala)|"
               r"hip hop (?:mexicano|chileno|argentino|colombiano|cubano|peruano|venezolano|boricua|tijuanense)|"
               r"spanish hip hop|latin rap|\burbano\b|zhenskiy rep"),
    ("mexico", r"mexican|mexicano|mexicana|\bbanda\b|norteno|nortena|corrido|mariachi|ranchera|grupera|duranguense|tejano|"
               r"tex-mex|sierreno|tamborazo|huapango|cumbia sonidera|son jarocho|trova yucateca|tribal guarachero|"
               r"requinto|sonidero|banda sinaloense|chicano|tierra caliente|son huasteco|\bpasito|tololoche|"
               r"musica (?:chihuahuense|sonorense|bajacaliforniana|tlaxcalteca|tamaulipeca|sinaloense|poblana|potosina|"
               r"coahuilense|neoleonesa|duranguense|zacatecana|jalisciense|michoacana|guerrerense|oaxaquena|veracruzana|"
               r"hidalguense|queretana|sudcaliforniana|tabasquena|yucateca|chiapaneca|campechana|nayarita|colimense|"
               r"aguascalentense|guanajuatense|mexiquense|morelense|quintanarroense)|tecnobanda|\bchilena\b|\btrival\b"),
    ("cumbia", r"cumbia|vallenato|chicha|\bporro\b|champeta|tecnocumbia|cuarteto|guaracha\b|chucu|\bgaita\b(?! gallega)|"
               r"currulao|bullerengue|musica tropical|tropical (?:colombiano|peruano|boliviano)|musica costena|"
               r"musica popular colombiana|^tropical$|tropical tecladista"),
    ("bachata", r"bachata|merengue|dominican|dominicano|mambo urbano|perico ripiao|\bsalve\b"),
    ("salsa", r"salsa|timba|son cubano|\bmambo|cha-cha|bolero|guaguanco|rumba cubana|danzon|guajira|charanga|boogaloo|"
              r"musica cubana|\bcuban|cubano|\btrova|filin|latin big band|pachanga|\bsongo\b"),
    ("tango", r"tango|milonga|orquesta tipica"),
    ("andes", r"andean|andina|andino|folklore (?:argentino|chileno|peruano|boliviano|ecuatoriano|venezolano|colombiano|"
              r"paraguayo|uruguayo|cuyano|santiagueno|salteno|tucumano|riojano|latinoamericano)|folclore|chacarera|"
              r"\bcueca|huayno|\bsaya\b|caporal|morenada|\bzamba\b|chamame|carnavalito|musica criolla|joropo|llanera|"
              r"nueva cancion|vals peruano|marinera|tonada|festejo|\blando\b|taquirari|bambuco|pasillo|sanjuanito|"
              r"guarania|polka paraguaya|harpa paraguaia|charango|\bquena|zampona|folclor\b|folclor afro|canto popular uruguayo|plena uruguaya|musica popular uruguaya|cuatro venezolano|musica ayacuchana|musica afroperuana"),
    ("latinrock", r"rock en espanol|latin rock|latin alternative|latin indie|"
                  r"(?:rock|indie|pop rock|post-punk|metal) (?:argentino|chileno|mexicano|colombiano|peruano|uruguayo|"
                  r"venezolano|boliviano|espanol|paraguayo|ecuatoriano|costarricense|guatemalteco|hondureno|salvadoreno|"
                  r"nicaraguense|panameno|dominicano|cordoba|catala|gallego|vasco|andaluz|canario|puertorriqueno)|"
                  r"rock urbano|rock nacional|rock alternativo|nueva ola|movida|latintronica|tropical alternativo"),
    ("latinpop", r"latin pop|pop latino|balada|latin ballad|cantautor|romantico|romantica|latin arena pop|"
                 r"latin viral pop|latin afrobeat|latin christian|grupero romantico|tropipop|canadian latin|"
                 r"pop (?:venezolano|chileno|argentino|colombiano|peruano|mexicano|uruguayo|paraguayo|boliviano|"
                 r"ecuatoriano|costarricense|dominicano|puertorriqueno|guatemalteco|hondureno|salvadoreno|panameno|"
                 r"nicaraguense|espanol|catala|gallego|vasco|canario|andaluz)|musica catalana|musica aragonesa|telepop|musica canaria"),
    ("dancehall", r"dancehall|ragga|bashment|soundsystem|sound system|shatta|basshall|trinibad"),
    ("ska", r"\bska\b(?! punk|-punk|core)|rocksteady|2 tone|two tone|skinhead reggae|bluebeat"),
    ("soca", r"soca|calypso|chutney|steelpan|steel band|bouyon|\bmento\b|parang|kaiso|rapso"),
    ("zouk", r"zouk|kompa|konpa|kizomba|semba|kuduro|gwo ka|\bbele\b|biguine|haitian|antillais|antilles|martiniqu|"
             r"guadeloup|creole|cadence|compas|angolan|angolana|twoubadou"),
    ("reggae", r"roots reggae|lovers rock|\bdub\b(?! techno| house)|reggae|nyahbinghi|jawaiian"),
    ("amapiano", r"amapiano|gqom|kwaito|bacardi|afro house|south african house|sgija|deep afro|afro tech"),
    ("afrobeats", r"afrobeats|afropop|afro pop|naija|\balte\b|afro r&b|afroswing|afro dancehall|afro soul|afro-soul|"
                  r"azonto|afro trap|afro drill|gengetone|bongo flava|singeli|nigerian|ghanaian|afrofuturism"),
    ("afrobeat", r"afrobeat|highlife|afro-funk|afro funk|afro-jazz|afro jazz|\bjuju\b|\bfuji\b|apala|palm wine|"
                 r"afro-cuban|afro psych|afro rock|afro-rock|hiplife"),
    ("rumba", r"rumba congolaise|soukous|ndombolo|makossa|bikutsi|coupe-decale|coupe decale|zouglou|congo|"
              r"rumba(?! flamenca| catalana| cubana)|seben|kwassa|mapouka|assiko|musique urbaine kinshasa"),
    ("latinscenes", r"^musica \w+(?:ense|ana|ano|ena|eno|ina|ino|eca|eco)$|\btipico\b|ritmo kombina|plena\b"),
    ("africascenes", r"musica santomense|musica (?:mocambicana|guineense|caboverdiana)|maimouna"),
    ("eastafrica", r"ethio|ethiopian|eritrean|somali|tigrigna|oromo|amharic|taarab|kenyan|ugandan|tanzanian|rwandan|"
                   r"burundi|malagasy|benga|chimurenga|mbira|zimbabw|zambian|malawi|mozambi|marrabenta|sudanese|"
                   r"kidandali|kadongo|zilizopendwa|shona|\bzulu|xhosa|maskandi|mbaqanga|isicathamiya|\bsotho|tswana|"
                   r"south african|afrikaans|namibian|botswana|swazi|lesotho|comorian|reunion|maloya|sega\b|mauritian"),
    ("westafrica", r"mbalax|\bmande\b|manding|griot|\bkora\b|wassoulou|malian|senegal|guinean|ivorian|burkin|\bniger\b|"
                   r"nigerien|gambian|tuareg|desert blues|tishoumaren|sahel|hausa|yoruba|\bigbo|beninese|togolese|"
                   r"cameroon|cape verde|cabo verde|morna|funana|coladeira|batuque|sierra leone|liberian|mauritania|"
                   r"gabon|west african|african\b"),
]

# 2. Heads, read from the end of the name: the match that ends last wins, then the longest
#    ("pop punk" is punk, "dance pop" is pop, "indie rock" is indie rock rather than rock).
HEADS: list[tuple[str, str]] = [
    # electronic
    ("dnb", r"drum and bass|drum'n'bass|\bdnb|jungle|liquid funk|neurofunk|jump up|darkstep|halftime|footwork|juke"),
    ("hard", r"hardstyle|gabber|happy hardcore|frenchcore|uptempo|hard dance|jumpstyle|hardcore techno|speedcore|"
             r"terrorcore|rawstyle|xtra raw|hard bass|makina|hardtek|tekno|\btekk|breakcore|\brave\b|russian rave"),
    ("trance", r"trance|psytrance|\bgoa\b|psybient|psychill|full-on|uplifting|full on"),
    ("techno", r"techno|\bminimal\b|\bacid\b|schranz|dub techno|microhouse|bleep|ghettotech|detroit|berlin|"
               r"dark clubbing|klubowe"),
    ("house", r"house|garage house|jackin|ballroom|\bvogue|chicago|balearic|filter|french touch|lo-fi house"),
    ("bass", r"dubstep|bass music|brostep|riddim|future bass|uk bass|\bwave\b|midtempo|bass trap|edm trap|melodic bass|"
             r"bass house|\bneuro\b|wonky|future garage|deconstructed club|\bclub\b|jersey club|baltimore club|\bbass\b|"
             r"chillstep|filthstep|\bstep\b|\w+step\b"),
    ("breaks", r"breakbeat|breaks|uk garage|\bukg\b|2-step|speed garage|bassline|uk funky|nu skool|big beat"),
    ("edm", r"\bedm\b|big room|electro house|complextro|eurodance|euro dance|hands up|\bdance\b|electro latino|"
            r"melbourne bounce|slap house|tropical house|pop edm|festival|\bbounce\b|hi-nrg|italo dance|eurobeat|"
            r"dancefloor|vinahouse|circuit|\bcedm\b|\bepa\b|techengue"),
    ("disco", r"disco|nu-disco|french house|\bitalo\b|cosmic|post-disco"),
    ("ambient", r"ambient|space music|spacesynth|ambient folk|fourth world|atmosphere"),
    ("downtempo", r"downtempo|trip hop|chillout|chill out|lounge|lo-fi beats|\blofi\b|\blo-fi\b|chillhop|chill beats|"
                  r"chillwave|electronic chill|\bchill\b|\bbeats\b"),
    ("synth", r"synthwave|retrowave|darksynth|outrun|vaporwave|hardvapour|electroclash|\belectro\b|electro-industrial|"
              r"italo synth|cyberpunk|future funk|chillsynth|\bsynth\b|synthesizer|nightrun|(?:hard|pop|space|soviet|dream|future|chill|night|trap|vapor|retro|synth|tech)wave\b|mallsoft|utopian virtual"),
    ("industrial", r"industrial|\bebm\b|aggrotech|dark electro|witch house|power electronics|futurepop|"
                   r"electronic body|martial|neue deutsche harte"),
    ("electronica", r"\bidm\b|intelligent dance music|glitch|braindance|electronica|electronic\b|electroacoustic|"
                    r"electronic experimental|modular|electronique|folktronica|livetronica|ethnotronica|"
                    r"aussietronica|indietronica|\w+tronica\b"),
    # metal (before rock and punk: "punk metal" is metal)
    ("metalcore", r"metalcore|deathcore|mathcore|easycore|djentcore|electronicore|nintendocore|crabcore|trancecore"),
    ("progmetal", r"progressive metal|djent|avant-garde metal|tech metal|technical metal"),
    ("grind", r"grindcore|goregrind|powerviolence|deathgrind|cybergrind|pornogrind|noisecore|\bcrust"),
    ("black", r"black metal|blackgaze|depressive|\bdsbm\b|war metal|pagan black|atmospheric black|black thrash|black'n'roll"),
    ("death", r"death metal|death'n'roll|\bbrutal|\bslam\b|melodeath|melodic death|technical death|swedish death|"
              r"old school death|death doom|deathrash|\bgore"),
    ("doom", r"\bdoom|sludge|stoner|drone metal|funeral|desert rock|post-metal|atmospheric sludge|heavy psych|\bfuzz|palm desert"),
    ("folkmetal", r"folk metal|pagan|viking|celtic metal|medieval metal|oriental metal|pirate metal|epic metal"),
    ("power", r"power metal|symphonic metal|gothic metal|melodic metal|neoclassical metal|\bepic\b"),
    ("thrash", r"thrash|groove metal|crossover thrash|speed metal|teutonic|bay area"),
    ("numetal", r"nu metal|alternative metal|rap metal|funk metal|industrial metal|nu-metal|neue deutsche harte|"
                r"rap rock|nu-core|alt metal"),
    ("heavy", r"heavy metal|nwobhm|traditional heavy|glam metal|hair metal|\bmetal\b|metallic|\bheavy\b|shred|slayer"),
    # punk
    ("posthardcore", r"post-hardcore|screamo|emoviolence|swancore|melodic hardcore|skramz"),
    ("poppunk", r"pop punk|pop-punk|\bemo\b|midwest emo|skate punk|neon pop punk|punk melodico|dreamo"),
    ("skapunk", r"ska punk|skacore|ska-punk"),
    ("garagepunk", r"garage punk|psychobilly|horror punk|surf punk|cowpunk|gypsy punk|folk punk|celtic punk|"
                   r"punk blues|egg punk|synth punk|gothabilly"),
    ("hardcore", r"hardcore|beatdown|d-beat|youth crew|straight edge|thrashcore|power violence|\bnyhc|tough guy"),
    ("punkrock", r"punk|\boi\b|street punk|riot grrrl|anarcho|queercore|proto-punk|charva"),
    # hip hop
    ("drill", r"drill"),
    ("cloud", r"cloud rap|emo rap|sad rap|phonk|plugg|\brage\b|digicore|hyperpop|glitchcore|underground rap|"
              r"soundcloud|lo-fi rap|memphis|vapor trap|\btread|\bjerk\b|hexd|sigilkore|krushclub|\bzxc\b|scenecore|\bdrift\b|\bdrain\b|futuristic swag"),
    ("trap", r"\btrap\b|crunk|chopped|screwed|trap soul|melodic trap|\w*trap\b"),
    ("uk", r"grime|uk hip hop|road rap|uk rap|british hip hop|scottish hip hop|irish hip hop|welsh hip hop|"
           r"uk alternative hip hop|afroswing"),
    ("frenchrap", r"rap francais|french hip hop|rap conscient|rap quebecois|belgian hip hop|rap belge|swiss hip hop|"
                  r"rap (?:marseille|lyonnais|toulousain|nantais|parisien|lillois|bordelais|montpellierain|rennais|"
                  r"strasbourgeois|nicois|ivoire|senegalais|algerien|marocain|tunisien|camerounais|congolais|"
                  r"malgache|gabonais|guineen|burkinabe|malien|antillais|reunionnais|guyanais|calme|francophone|"
                  r"suisse|romand|haitien|creole|independant|alternatif francais|old school francais)|"
                  r"french rap|pop urbaine|drill francaise|rap 2000"),
    ("south", r"southern hip hop|dirty south|gangster|gangsta|g funk|g-funk|west coast|hyphy|bay area hip hop|"
              r"atl hip hop|houston|chicano rap|texas|nola|new orleans|miami|florida|detroit hip hop|st louis|"
              r"kentucky|louisiana|chicago rap|vegas|cali rap|westcoast flow"),
    ("boombap", r"boom bap|old school hip hop|golden age|east coast|hardcore hip hop|nyc rap|queens|brooklyn|bronx|"
                r"harlem|philly rap|boston hip hop|instrumental hip hop|turntablism|breakdance|b-boy|bboy|"
                r"electro hip hop|popping"),
    ("althiphop", r"alternative hip hop|underground hip hop|abstract|conscious|experimental hip hop|jazz rap|"
                  r"political hip hop|indie hip hop|nerdcore|horrorcore|lo-fi hip hop|psychedelic hip hop|"
                  r"christian hip hop|gospel rap|deep underground|rap underground|hip hop experimental|alternative rap"),
    ("poprap", r"pop rap|melodic rap|rap pop|hip pop|viral rap|rap romantico|rap romantique|pop urbano|"
               r"hip hop|hip-hop|\brap\b|rapper|\bmc\b|hiphop|\brep\b|\w+rap\b|\w+hop\b(?<!barbershop)"),
    # r&b
    ("neosoul", r"neo soul|neo-soul|alternative r&b|indie r&b|r&b alternative|dark r&b|bedroom soul|psychedelic soul"),
    ("slow", r"new jack swing|quiet storm|slow jam|freestyle|urban contemporary"),
    ("doowop", r"doo-wop|doo wop|vocal harmony|barbershop|a cappella|acapella"),
    ("funk", r"\bfunk\b|p funk|go-go|electro funk|deep funk|minneapolis|boogie\b|funk rock|\bstrut|rare groove"),
    ("soul", r"\bsoul\b|motown|northern soul|philly soul|southern soul|deep soul|chicago soul|memphis soul|"
             r"rhythm and blues|classic r&b|retro soul|blue-eyed|souldies"),
    ("rnbnow", r"r&b|\brnb\b|contemporary r&b|\burban\b|pluggnb|trap soul"),
    # jazz
    ("latinjazz", r"latin jazz|afro-cuban jazz|cubop|jazz cubano"),
    ("smooth", r"smooth jazz|smooth saxophone|quiet jazz|jazz pop"),
    ("fusion", r"jazz fusion|jazz funk|jazz-funk|acid jazz|nu jazz|jazz rock|jazz-rock|broken beat|jazztronica|"
               r"future jazz|electro jazz|jazz house|crossover jazz|jazz boom bap|jam band"),
    ("free", r"free jazz|avant-garde jazz|spiritual jazz|loft jazz|creative jazz|experimental jazz"),
    ("swing", r"\bswing\b|big band|dixieland|ragtime|\bstride\b|gypsy jazz|jazz manouche|trad jazz|early jazz|"
              r"new orleans jazz|hot jazz|\bjive\b|lindy|electro swing|western swing"),
    ("vocaljazz", r"vocal jazz|adult standards|crooner|easy listening|exotica|\btorch|cocktail|space age pop|standards|"
                  r"jazz vocal|jazz singer|jazz chanteuse"),
    ("cool", r"cool jazz|\bmodal\b|third stream|west coast jazz|chamber jazz|\becm\b"),
    ("bop", r"bebop|hard bop|post-bop|\bbop\b|soul jazz|jazz trumpet|jazz saxophone|jazz organ|jazz trombone|"
            r"jazz clarinet|jazz vibraphone|straight-ahead"),
    ("modernjazz", r"\bjazz\b|contemporary jazz|modern jazz|jazz piano|jazz guitar|jazz trio|jazz quartet|jazz bass|"
                   r"jazz drums|jazz double bass|jazz harp|jazz flute|jazz violin|jazz accordion"),
    # blues
    ("bluesrock", r"blues rock|british blues|boogie rock|blues-rock"),
    ("soulblues", r"soul blues|swamp blues|\bswamp\b|zydeco|cajun|louisiana blues|jump blues"),
    ("delta", r"delta blues|country blues|acoustic blues|piedmont|pre-war|traditional blues|hill country|"
              r"harmonica blues|blues harmonica|slide guitar|fingerstyle blues"),
    ("electricblues", r"\bblues\b"),
    # country
    ("bluegrass", r"bluegrass|old-time|old time|appalachian|newgrass|banjo|\bmountain|jug band|string band|deathgrass|\w*grass\b"),
    ("americana", r"americana|alt-country|alternative country|red dirt|texas country|outlaw|roots rock|heartland|"
                  r"gothic americana|country rock|insurgent|north carolina roots|wyoming roots|new mexico music"),
    ("classiccountry", r"classic country|honky tonk|honky-tonk|nashville sound|cowboy|\bwestern\b|bakersfield|"
                       r"countrypolitan|traditional country|yodeling|truck|old west"),
    ("moderncountry", r"contemporary country|country pop|modern country|country road|bro-country|country dawn|"
                      r"country rap|redneck|hick hop|\bcountry\b|countrygaze"),
    # rock
    ("postrock", r"post-rock|math rock|noise rock|experimental rock|avant-rock|instrumental rock|art punk|zolo|post rock"),
    ("postpunk", r"post-punk|new wave|darkwave|coldwave|\bgothic\b|\bgoth\b|minimal wave|deathrock|no wave|dark wave|"
                 r"neue deutsche welle|batcave|ethereal wave|cold wave|new romantic|melancholia|antideutsche|todeskunst"),
    ("prog", r"progressive rock|\bprog\b|art rock|symphonic rock|canterbury|zeuhl|krautrock|rock in opposition|"
             r"progressive|neo-prog|space rock|\bprogg\b"),
    ("psych", r"\bpsych|psychedelic|garage rock|acid rock|freakbeat|garage\b|surf rock|\bsurf\b|neo-psychedelic|"
              r"stoner rock|nuggets|\b60s\b|\bbeat\b|merseybeat|british invasion|\bmod\b|sunshine pop|jangle|paisley|"
              r"beatlesque"),
    ("hardrock", r"hard rock|\bglam\b|\baor\b|arena rock|sleaze|cock rock|pub rock|boogie"),
    ("altrock", r"alternative rock|grunge|post-grunge|britpop|madchester|modern rock|permanent wave|alternative\b|"
                r"alt-rock|alt rock|modern alternative|90s alternative"),
    ("rocknroll", r"rock-and-roll|rock and roll|rock'n'roll|rockabilly|skiffle|\btwist\b|neo-rockabilly|teddy boy|"
                  r"swamp rock|rockin"),
    ("poprock", r"pop rock|power pop|soft rock|yacht rock|mellow gold|adult album alternative|piano rock|"
                r"acoustic rock|melodic rock|light rock|supergroup"),
    ("classicrock", r"classic rock|album rock|southern rock|heartland rock|\brock\b|\broll\b|\w+rock\b|nwocr"),
    # indie
    ("shoegaze", r"shoegaze|nu gaze|slowcore|sadcore|dreamgaze|\bgaze\b|space pop|\w*gaze\b"),
    ("lofi", r"bedroom|lo-fi indie|lo-fi pop|slacker|\btape\b|homemade|\bdiy\b"),
    ("indietronica", r"indie electronic|electronic indie|electropop indie|indie dance|dance-punk|nu rave|new rave|"
                     r"indie electro|indiecoustica"),
    ("indiepop", r"indie pop|dream pop|\btwee|jangle pop|\bc86\b|noise pop|chamber pop|baroque pop|indie poptimism|"
                 r"bubblegrunge|pov: indie|indie folk pop|indie soul|\balt z\b|modern indie pop|\bpixie\b|elephant 6"),
    ("indierock", r"indie rock|indie garage|indie punk|indie psych|indie emo|indie surf|indie anthem|garage pop|"
                  r"modern indie rock|\w+indie\b"),
    ("alternative", r"alternative pop rock|alternative indie|alternative dance"),
    ("indierock", r"\bindie\b"),
    # folk
    ("indiefolk", r"indie folk|freak folk|stomp and holler|stomp and flutter|folk-pop|folk pop|chamber folk|new weird|"
                  r"psych folk|psychedelic folk|anti-folk|neofolk|dark folk|apocalyptic folk|pastoral"),
    ("folkrevival", r"folk revival|traditional folk|british folk|american folk|contemporary folk|protest|folk rock|"
                    r"old folk|folk baroque|acid folk|progressive folk|medieval folk|renaissance fair|filk|"
                    r"\bfolk\b|folklore|traditional\b|shanty|hurdy-gurdy|\w+folk\b|folkmusik"),
    ("songwriter", r"singer-songwriter|songwriter|cantautor|cantautora|canzone d'autore|liedermacher|\bvisor|"
                   r"vispop|auteur|acoustic\b|unplugged|women's music"),
    # pop
    ("asianpop", r"k-pop|j-pop|c-pop|mandopop|cantopop|v-pop|t-pop|p-pop|thai pop|k-indie|j-rock|k-rock|j-pixie|"
                 r"j-rap|k-rap|k-ballad|japanese|korean|chinese|taiwan|hong kong|mandarin|cantonese|idol|city pop|"
                 r"shibuya-kei|visual kei|j-indie|j-metal|j-punk|anime pop|\bsino|zhongguo feng|\w+-kei\b|denpa"),
    ("chanson", r"chanson|variete|schlager|canzone|levenslied|dansband|dansktop|nederpop|kleinkunst|estrada|eurovision|"
                r"musica ligera|french pop|nouvelle chanson|varieta|chanteur|chanteuse|cantante|cancion|deutschpop|"
                r"liedjes|smartlap|volkstum|iskelma|\bye ye\b|neomelodici|mundart|huzunlu|sarkilar|\blata\b|danseband|streektaal|piratenmuziek|tin pan"),
    ("synthpop", r"synthpop|synth-pop|electropop|electro pop|new wave pop|hyperpop pop|sophisti-pop|dark pop|electro-pop|"
                 r"alt-pop|alternative pop|nu-wave|metropopolis"),
    ("artpop", r"art pop|experimental pop|avant-pop|\bbaroque\b(?! music)|progressive pop|chamber|orchestral pop"),
    ("softpop", r"adult contemporary|acoustic pop|neo mellow|lilith|piano pop|soft pop|easy pop|\bballad|\bmellow\b|"
                r"lounge pop|pop soul"),
    ("dancepop", r"dance pop|pop dance|post-teen pop|teen pop|boy band|girl group|europop|viral pop|\bpop\b|bubblegum|"
                 r"disney|pop edm|\bsummer\b|sped up|\bslowed\b|tiktok|\w+pop\b"),
    # classical
    ("choral", r"choir|choral|chorus|boys choir|chorale|vocal ensemble|chamber choir|\bchor\b|puirt-a-beul"),
    ("opera", r"opera|operatic|\blied|art song|soprano|tenor|baritone|mezzo|countertenor|zarzuela|\bmelodie\b|bel canto|"
              r"\bvocal\b"),
    ("early", r"medieval|renaissance|\bbaroque\b|early music|polyphony|ars nova|\blute\b|\bviol\b|harpsichord|madrigal|"
              r"troubadour|minnesang|cantigas|period instrument|galante"),
    ("contemporary", r"contemporary classical|20th century|21st century|avant-garde classical|serialism|spectral|"
                     r"minimalism|post-minimalism|minimal classical|new complexity|atonal|modernism|"
                     r"contemporary composition|experimental classical|microtonal|darmstadt"),
    ("neoclassical", r"neoclassical|neo-classical|neo classical|modern classical|compositional ambient|"
                     r"classical crossover|cinematic classical|epic classical|post-classical|ambient classical|"
                     r"new classical|piano cover|neoclassicism|pianissimo"),
    ("solo", r"classical piano|classical guitar|violin|cello|\bviola\b|\bharp\b|\borgan\b|\bflute|clarinet|oboe|bassoon|"
             r"trumpet|\bhorn\b|trombone|\btuba|saxophone|percussion|marimba|\bguitar\b|\bpiano\b|accordion|"
             r"mandolin|recorder|guitarra|piano solo|\bsolo\b|instrumental|fingerstyle"),
    ("orchestral", r"orchestra|orchestral|symphony|symphonic|chamber music|string quartet|ensemble|quartet|\btrio\b|"
                   r"quintet|wind ensemble|\bbrass\b|strings|philharmonic|sinfonia|camerata|consort|octet|string duo|orchestr"),
    ("romantic", r"classical\b|romantic|romanticism|classical era|late romantic|classical period|impressionism|"
                 r"post-romantic|classique|klassik|klassisk|clasica|classica|klasyczna|klasszikus|composer|"
                 r"composition|nationalism|verismo|biedermeier"),
    # experimental
    ("noise", r"noise|harsh|power electronics|japanoise"),
    ("drone", r"drone|lowercase|microsound|minimal drone|onkyo"),
    ("soundart", r"sound art|musique concrete|field recording|tape music|acousmatic|plunderphonics|sound collage|"
                 r"sound design|radiophonic|sound poetry|soundscape|found sound|hauntology"),
    ("improv", r"free improvisation|improvisation|\beai\b|improv"),
    ("avant", r"avant-garde|experimental|outsider|\bavant\b|fluxus|art music|weird|\bdada|oddity|multidisciplinary"),
]

# 3. Traditions of a part of the world: used when the name has no modern head ("turkish folk",
#    "bollywood", "georgian polyphony"), never for a scene of a modern genre ("turkish rock").
WORLD: list[tuple[str, str]] = [
    ("celtic", r"celtic|irish folk|scottish folk|sea shant|shanties|bagpipe|gaelic|welsh folk|cornish|manx|ceilidh|"
               r"trad irish|irish trad|bodhran|tin whistle|\bfiddle|uilleann|cape breton|irish|scottish|breton"),
    ("mideast", r"arab|khaleeji|khaliji|mahraganat|egyptian|shaabi|lebanese|syrian|iraqi|jordanian|palestin|saudi|"
                r"yemeni|kuwaiti|emirati|bahraini|omani|qatari|maghreb|moroccan|algerian|tunisian|libyan|\brai\b|gnawa|"
                r"chaabi|amazigh|kabyle|berber|turkish|\bturk\b|turku|oyun havasi|arabesk|anatolian|persian|iranian|"
                r"kurdish|armenian|israeli|mizrahi|hebrew|dabke|tarab|maqam|\boud\b|\bney\b|zaffa|sharqi|baladi|mawwal|"
                r"halay|azeri|azerbaijan|afghan|pashto|\bdari\b|tajik|baluchi|assyrian|levant|bedouin|cypriot|\brif\b|turkce|baglama|bozlak|dakke dak"),
    ("southasia", r"bollywood|filmi|carnatic|hindustani|ghazal|bhangra|punjabi|tamil|telugu|kannada|malayalam|marathi|"
                  r"bengali|gujarati|\bodia|assamese|bhojpuri|rajasthani|haryanvi|garhwali|kumaoni|\bdesi\b|indian\b|"
                  r"sitar|tabla|sarod|santoor|veena|\bdhol|pakistani|urdu|sindhi|nepali|sri lankan|sinhala|\bbaila\b|"
                  r"bangladeshi|tollywood|kollywood|sandalwood|mollywood|lavani|dandiya|garba|indipop|rabindra"),
    ("seasia", r"dangdut|kroncong|keroncong|gamelan|jaipong|campursari|koplo|luk thung|mor lam|molam|\bthai\b|\blao\b|"
               r"laotian|khmer|cambodian|vietnamese|cai luong|filipino|pinoy|\bopm\b|kundiman|papuri|\bmalay\b|"
               r"malaysian|indonesian|javanese|sundanese|balinese|minang|batak|bugis|\blagu\b|singaporean|burmese|"
               r"myanmar|timor|brunei|hmong|phleng|manila sound|viet\b"),
    ("eastasia", r"\benka\b|kayokyoku|minyo|shamisen|\bkoto\b|shakuhachi|taiko|japanese|chinese|guzheng|erhu|\bpipa\b|"
                 r"peking opera|cantonese opera|gugak|pansori|\btrot\b|korean|mongolian|tibetan|uyghur|okinawan|"
                 r"\bainu\b|kabuki|\bnoh\b|gagaku|hokkien|taiwanese|nanguan|xiqu|kunqu"),
    ("central", r"kazakh|uzbek|kyrgyz|turkmen|tatar|bashkir|chechen|dagestan|ossetian|kavkaz|caucas|georgian|tuvan|"
                r"throat singing|yakut|sakha|buryat|altai|mugham|mugam|ashik|chuvash|udmurt|\bmari\b|kalmyk"),
    ("balkans", r"balkan|turbo-folk|turbo folk|manele|sevdah|sevdalinka|narodna|starogradska|chalga|bulgarian|"
                r"romanian|muzica populara|lautareasca|gypsy|romani|\broma\b|tamburica|klapa|kafana|novokomponovana|"
                r"albanian|kosovar|macedonian|serbian|croatian|bosnian|montenegr|slovenian|greek|rebetiko|\blaiko|"
                r"entechno|entehno|nisiotika|ukrainian|russian|chastushki|shanson|\bbard\b|polish|disco polo|czech|"
                r"slovak|hungarian|csardas|moldovan|belarusian|lithuanian|latvian|estonian|klezmer|yiddish|cimbalom|tallava|poezja spiewana"),
    ("europe", r"fado|flamenco|rumba flamenca|copla|sevillanas|\bjota\b|cante\b|cancion espanola|\btuna\b|bretonne|"
               r"occitan|corsican|\bcorse\b|basque|euskal|galician|gaita gallega|sardinian|neapolitan|napoletan|"
               r"tarantella|pizzica|tammurriata|liscio|polka|oberkrain|volksmusik|volkstumliche|schuhplattler|yodel|"
               r"jodel|alpine|swiss|landler|musette|accordion|accordeon|bal folk|nordic|joik|yoik|kveding|"
               r"hardingfele|nyckelharpa|swedish|norwegian|danish|finnish|faroese|icelandic|scandinavian|dutch|"
               r"smartlap|levenslied|portuguese|pimba|maltese|walloon|frisian|saami|\bsami\b|german|austrian|"
               r"bavarian|italian|french|spanish|english|belgian|luxembourg|nova canco|mestissatge|norske viser|skansk|rogaland|trondersk|nordnorsk|seemann|zillertal|blaskapelle|musica sarda|musica madeirense|victorian"),
    ("oceania", r"maori|hawaiian|aboriginal|indigenous|pacific island|polynesian|samoan|tongan|fijian|tahitian|papua|"
                r"melanesian|native american|first nations|inuit|powwow|pow wow|navajo|lakota|cherokee|mapuche|quechua|"
                r"aymara|kanaka|torres strait|slack key|ukulele|didgeridoo|metis|world fusion|\bworld\b|kaneka"),
]

_RULES = [(sub, re.compile(pattern)) for sub, pattern in RULES]
_HEADS = [(sub, re.compile(pattern)) for sub, pattern in HEADS]
_WORLD = [(sub, re.compile(pattern)) for sub, pattern in WORLD]
# A generic head after a place is that genre's scene somewhere ("swedish pop", "bristol indie").
SCENE_OF = {"dancepop": "worldpop", "classicrock": "rockscenes", "heavy": "metalscenes", "punkrock": "punkscenes",
            "hardcore": "punkscenes", "poprap": "rapscenes", "rnbnow": "rnbscenes", "modernjazz": "jazzscenes",
            "folkrevival": "folkscenes", "moderncountry": "countryscenes", "electronica": "elscenes",
            "reggae": "reggaescenes", "romantic": "classicalscenes", "indierock": "indiescenes"}
# Heads that give way to a tradition of a part of the world ("turkish folk" is Middle East, not folk).
TRADITIONAL = {"folkrevival"}
# Generic heads ("metal", "rock", "hip hop"…): a more precise word of the same main genre wins over them.
GENERIC = set(SCENE_OF) | {"electricblues"}


def _plain(name: str) -> str:
    return unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()


def _head(n: str) -> tuple[str | None, int]:
    """The sub-genre of the head of a (plain) name, and where that head starts. A generic head
    gives way to a precise word of the same main genre ("thrash metal" is thrash, not metal)."""
    found = [(m.end(), -m.start(), i, sub) for i, (sub, rx) in enumerate(_HEADS) for m in rx.finditer(n)]
    if not found:
        return None, len(n)
    end, neg_start, _, best = max(found, key=lambda f: (f[0], f[1], -f[2]))
    if best in GENERIC:
        precise = [f for f in found if f[3] not in GENERIC and SUB[f[3]][0] == SUB[best][0]]
        if precise:
            return max(precise, key=lambda f: (f[0], f[1], -f[2]))[3], len(n)
    return best, -neg_start


def by_rules(name: str) -> str | None:
    """The sub-genre a genre's name points to, or None when no rule recognises it."""
    from core.soundmap import _is_region, _local_scene

    n = _plain(name)
    for sub, rx in _RULES:
        if rx.search(n):
            return sub
    head, at = _head(n)
    if head is None or head in TRADITIONAL:
        for sub, rx in _WORLD:
            if rx.search(n):
                return sub
    if head in SCENE_OF:
        before = [w.strip("-:") for w in n[:at].split()]
        after = n.split()[1:] if n.split()[0] in ("rap", "pop", "rock", "jazz", "indie", "metal", "punk") else []
        if any(_is_region(w) for w in before + after) or (before and _local_scene(name, set())):
            return SCENE_OF[head]
    return head


# --- every genre of the map in the tree --------------------------------------------------------------------

def classify(names: list[str], xy: np.ndarray, k: int = 9) -> list[str]:
    """The sub-genre of every genre: by its name, else the one most common among its nearest
    neighbours by sound (xy: Every Noise positions, 0..1)."""
    subs = [by_rules(n) for n in names]
    known = np.array([s is not None for s in subs])
    ref, ref_subs = xy[known], [s for s in subs if s is not None]
    for i in np.flatnonzero(~known):
        d = np.hypot(*(ref - xy[i]).T)
        votes: Counter = Counter()
        for j in np.argsort(d)[:k]:
            votes[ref_subs[j]] += 1.0 / (d[j] + 1e-3)
        subs[i] = votes.most_common(1)[0][0]
    return subs


# Hue of each main genre on the night-blue map (degrees), chosen so that each family reads at once
# and neighbours differ.
HUES = {"electronic": 192, "pop": 322, "indie": 258, "rock": 22, "metal": 352, "punk": 300, "hiphop": 36, "rnb": 278,
        "jazz": 46, "blues": 228, "country": 30, "folk": 80, "latin": 4, "brazil": 102, "caribbean": 142, "africa": 66,
        "world": 168, "classical": 52, "screen": 208, "sacred": 12, "experimental": 236, "other": 212}
LIGHT = {"metal": 58, "classical": 80, "sacred": 80, "experimental": 74, "other": 76, "blues": 70, "rock": 63, "latin": 63}


def _outline(n: int = 240) -> np.ndarray:
    """The edge of the atlas: a rounded continent whose coast wobbles a little (display space,
    x in 0..ASPECT, y in 0..1)."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    wobble = 1 + .035 * np.sin(3 * t + .7) + .025 * np.sin(5 * t + 2.1) + .012 * np.sin(11 * t + .3)
    c, s = np.cos(t), np.sin(t)
    r = wobble / (np.abs(c) ** 3.2 + np.abs(s) ** 3.2) ** (1 / 3.2)
    return np.stack([ASPECT / 2 + .47 * ASPECT * r * c, .5 + .46 * r * s], 1)


def _inside(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    x, y = pts[:, 0], pts[:, 1]
    hit = np.zeros(len(pts), bool)
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, 0)):
        cross = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1)
        hit ^= cross
    return hit


def _spread(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Positions by rank, spread evenly between lo and hi (keeps the order, not the crowding)."""
    if len(v) == 1:
        return np.array([(lo + hi) / 2])
    return lo + (hi - lo) * np.argsort(np.argsort(v, kind="stable"), kind="stable") / (len(v) - 1)


def _balance(pts: np.ndarray, seeds: np.ndarray, share: np.ndarray, iters: int = 60) -> np.ndarray:
    """Give each seed a contiguous part of `pts` of the wanted share: a power diagram whose
    weights grow for the seeds that have too little, with the seeds moving to their centroid."""
    seeds = seeds.astype(float).copy()
    share = share / share.sum()
    area = np.ptp(pts[:, 0]) * np.ptp(pts[:, 1]) or 1.0
    w = np.zeros(len(seeds))
    lab = np.zeros(len(pts), int)
    for it in range(iters):
        d2 = ((pts[:, None, :] - seeds[None, :, :]) ** 2).sum(-1) - w[None, :]
        lab = d2.argmin(1)
        got = np.bincount(lab, minlength=len(seeds)) / len(pts)
        w += 0.8 * area * (share - got) / np.pi
        if it % 3 == 2 and it < iters - 6:
            for j in range(len(seeds)):
                mine = pts[lab == j]
                if len(mine):
                    seeds[j] = 0.5 * seeds[j] + 0.5 * mine.mean(0)
    return lab


def build(grid: tuple[int, int] = (400, 250)) -> dict:
    """The tree and its atlas (see the module docstring)."""
    from core.soundmap import ASSET as MAP_ASSET

    data = json.loads(MAP_ASSET.read_text(encoding="utf-8"))
    names = [r[0] for r in data["genres"]]
    en = np.array([[r[2], r[3]] for r in data["genres"]], float)  # Every Noise, 0..1
    subs = classify(names, en)
    mains = [SUB[s][0] for s in subs]

    xs = (np.arange(grid[0]) + .5) / grid[0] * ASPECT
    ys = (np.arange(grid[1]) + .5) / grid[1]
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    outline = _outline()
    pts = pts[_inside(pts, outline)]

    main_keys = [m for m in MAIN if m in set(mains)]
    by_main = {m: [i for i, x in enumerate(mains) if x == m] for m in main_keys}
    cen = np.array([en[by_main[m]].mean(0) for m in main_keys])
    x0, x1, y0, y1 = pts[:, 0].min(), pts[:, 0].max(), pts[:, 1].min(), pts[:, 1].max()
    seeds = np.stack([_spread(cen[:, 0], x0 + .16 * (x1 - x0), x1 - .16 * (x1 - x0)),
                      _spread(cen[:, 1], y0 + .16 * (y1 - y0), y1 - .16 * (y1 - y0))], 1)
    lab_main = _balance(pts, seeds, np.array([len(by_main[m]) ** .8 for m in main_keys], float))

    pos = np.zeros((len(names), 2))
    out_main, out_sub = [], []
    sub_index: dict[str, int] = {}
    for mi, m in enumerate(main_keys):
        region = pts[lab_main == mi]
        members = by_main[m]
        sub_keys = [s for s in SUB if SUB[s][0] == m and any(subs[i] == s for i in members)]
        by_sub = {s: [i for i in members if subs[i] == s] for s in sub_keys}
        rx0, rx1, ry0, ry1 = region[:, 0].min(), region[:, 0].max(), region[:, 1].min(), region[:, 1].max()
        scen = np.array([en[by_sub[s]].mean(0) for s in sub_keys])
        guess = np.stack([_spread(scen[:, 0], rx0 + .2 * (rx1 - rx0), rx1 - .2 * (rx1 - rx0)),
                          _spread(scen[:, 1], ry0 + .2 * (ry1 - ry0), ry1 - .2 * (ry1 - ry0))], 1)
        snap = region[((region[:, None, :] - guess[None, :, :]) ** 2).sum(-1).argmin(0)]
        lab_sub = _balance(region, snap, np.array([len(by_sub[s]) ** .9 for s in sub_keys], float), iters=50)
        for si, s in enumerate(sub_keys):
            district = region[lab_sub == si]
            if not len(district):
                district = snap[si:si + 1]
            ids = by_sub[s]
            dx0, dx1, dy0, dy1 = district[:, 0].min(), district[:, 0].max(), district[:, 1].min(), district[:, 1].max()
            g = np.stack([_spread(en[ids, 0], dx0, dx1), _spread(en[ids, 1], dy0, dy1)], 1)
            gsnap = district[((district[:, None, :] - g[None, :, :]) ** 2).sum(-1).argmin(0)]
            if len(ids) > 1 and len(district) >= len(ids):
                lab_g = _balance(district, gsnap, np.ones(len(ids)), iters=30)
                for gi, i in enumerate(ids):
                    mine = district[lab_g == gi]
                    pos[i] = mine.mean(0) if len(mine) else gsnap[gi]
            else:
                pos[ids] = gsnap
            sub_index[s] = len(out_sub)
            out_sub.append({"key": s, "main": mi, "fr": SUB[s][1], "en": SUB[s][2],
                            "x": round(float(district[:, 0].mean() / ASPECT), 4), "y": round(float(district[:, 1].mean()), 4),
                            "n": len(ids)})
        out_main.append({"key": m, "fr": MAIN[m][0], "en": MAIN[m][1], "hue": HUES[m], "light": LIGHT.get(m, 66),
                         "x": round(float(region[:, 0].mean() / ASPECT), 4), "y": round(float(region[:, 1].mean()), 4),
                         "n": len(members)})
    return {"source": "Every Noise at Once genres, classified and laid out by core/genretree.py",
            "main": out_main, "sub": out_sub,
            "genres": [[n, sub_index[s], round(float(p[0] / ASPECT), 5), round(float(p[1]), 5)]
                       for n, s, p in zip(names, subs, pos)],
            "outline": [[round(float(x / ASPECT), 4), round(float(y), 4)] for x, y in outline]}


@lru_cache(maxsize=1)
def tree() -> dict:
    """The stored atlas (app/assets/genre_tree.json)."""
    return json.loads(ASSET.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def position() -> dict[str, tuple[float, float, int]]:
    """genre name -> (x, y, sub-genre index) on the atlas, 0..1."""
    return {g[0]: (g[2], g[3], g[1]) for g in tree()["genres"]}
