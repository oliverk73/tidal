# -*- coding: utf-8 -*-
"""
Long-form "Learn" articles (FAQ-style) for the tide site.

Each entry is a self-contained article. Articles render through
templates/learn_article.html; the index page templates/learn_hub.html
groups them by category.

Keep bodies as straight HTML so we can paste them into Jinja without
escaping. Length target: ~300-600 words per article.

Internal links to predictions use /prediction/<slug>; the slugs below
are best-effort matches against the station index. If a slug doesn't
resolve at render time, the link still 404s gracefully — non-critical.
"""

CATEGORIES = [
    ("basics",      "Tide basics"),
    ("phenomena",   "Phenomena & records"),
    ("predictions", "How predictions work"),
    ("currents",    "Tidal currents"),
    ("practice",    "Why it matters in practice"),
]

ARTICLES = [
    # ---------- BASICS ----------
    {
        "slug": "how-tides-work",
        "category": "basics",
        "title": "How do tides work?",
        "summary": "The Moon and Sun pull on the ocean, the Earth rotates underneath — and water piles up on opposite sides of the planet twice a day.",
        "body": """
<p>Tides are the rhythmic rise and fall of the sea caused mostly by the
gravitational pull of the <strong>Moon</strong> and, to a lesser extent, the
<strong>Sun</strong>. Because gravity weakens with distance, the side of the Earth
facing the Moon is pulled slightly harder than the centre, and the centre
slightly harder than the far side. That difference — the <em>tidal force</em>
— stretches the ocean into two bulges: one toward the Moon, one on the
opposite side.</p>

<p>As the Earth rotates once every 24 hours, any given coastline passes
through both bulges, producing roughly <strong>two high tides and two low tides
per day</strong>. The Moon itself moves along its orbit during that time, so the
cycle is actually about 24 h 50 min — which is why high tide arrives
about 50 minutes later each day.</p>

<h3>The Sun's role</h3>
<p>The Sun is much more massive than the Moon but also vastly farther away,
so its tidal effect is roughly 46 % of the Moon's. When Sun, Moon, and
Earth line up (new and full Moon), the two forces add — producing the
unusually large <a href="/learn/spring-neap-tides/">spring tides</a>. When
they pull at right angles (first and last quarter), the forces partly
cancel and we get the smaller <em>neap tides</em>.</p>

<h3>Why the tidal range varies so much by location</h3>
<p>On the open ocean the astronomical tide is only about half a metre
high. Coastal ranges are dramatically larger because the shape of basins,
the depth of the shelf, and the natural resonance of bays
<strong>amplify</strong> the tidal wave. The Bay of Fundy in Canada hits
<strong>16 m</strong> because its length and depth match the natural period of
the Atlantic tide — see
<a href="/learn/largest-tidal-ranges/">largest tidal ranges</a>. In contrast,
the Mediterranean has so little open connection to the Atlantic that
tides there are typically only 10–40 cm.</p>

<h3>What else affects sea level?</h3>
<p>The astronomical tide is predictable centuries in advance. But the
<em>actual</em> water level on any given day also depends on wind, air pressure,
river flow, and ocean currents. These non-astronomical effects are why
even the best
<a href="/learn/how-predictions-are-made/">tide prediction</a> can be off
by tens of centimetres during a storm — see
<a href="/learn/prediction-limits/">what predictions can and can't do</a>.</p>
""",
        "related": ["spring-neap-tides", "tide-types", "largest-tidal-ranges"],
    },
    {
        "slug": "tide-types",
        "category": "basics",
        "title": "Semidiurnal, diurnal, mixed — what are the tide types?",
        "summary": "Some coasts get two equal high tides a day, some get one, and some get two of very different size. Here's why.",
        "body": """
<p>If you walk the same beach every day, the daily tide pattern there
will fall into one of three categories — and that pattern is
remarkably stable, dictated by the geometry of the ocean basin.</p>

<h3>Semidiurnal tides</h3>
<p>Two high tides and two low tides each lunar day (24 h 50 min), with
the two highs of similar height and the two lows of similar height.
This is the textbook tide of the North Atlantic — places like
<strong>Bristol, Brest, Hamburg, Halifax</strong>. The interval between
successive high tides is about <strong>12 h 25 min</strong>.</p>

<h3>Diurnal tides</h3>
<p>Only one high and one low per day — about 24 h 50 min between high
tides. The astronomical forcing has both a semidiurnal and a diurnal
component, and in basins that resonate strongly at the diurnal period
(roughly 24 hours) the diurnal terms dominate. Examples:
<strong>the Gulf of Mexico, parts of South-East Asia and the
Karimata Strait</strong>.</p>

<h3>Mixed tides</h3>
<p>Two highs and two lows per day, but they are <strong>noticeably
unequal</strong>: a "higher high water" and a "lower high water"; same for
lows. Most of the US Pacific coast — including <strong>San Francisco,
Los Angeles, Seattle</strong> — has mixed tides. The difference between
the higher and lower high in Seattle can easily be 1.5 m.</p>

<h3>How we classify them</h3>
<p>Oceanographers use the <em>form number</em>
F = (K₁ + O₁) / (M₂ + S₂), the ratio of the two largest diurnal
constituents to the two largest semidiurnal ones:</p>
<ul>
  <li>F &lt; 0.25 → semidiurnal</li>
  <li>0.25 ≤ F &lt; 1.5 → mixed (mainly semidiurnal)</li>
  <li>1.5 ≤ F &lt; 3 → mixed (mainly diurnal)</li>
  <li>F ≥ 3 → diurnal</li>
</ul>

<p>F is derived from the
<a href="/learn/how-predictions-are-made/">harmonic constituents</a>
that come out of analysing a year or more of sea-level observations.
The form number is stable in time — a port's tide type does not change
between years — so once a station has been classified, that label
holds.</p>
""",
        "related": ["how-tides-work", "spring-neap-tides", "amphidromic-points"],
    },
    {
        "slug": "spring-neap-tides",
        "category": "basics",
        "title": "What are spring and neap tides?",
        "summary": "Twice a month, the tidal range swells; twice a month, it shrinks. The Moon's phase tells you which.",
        "body": """
<p>Despite the name, "spring tides" have nothing to do with the season.
The word here is the old Germanic <em>spring</em>, "to leap" — these are the
tides that <em>leap up</em> highest and drop lowest. Their counterpart, the
quieter <em>neap</em> tides, comes from an Old English word meaning
"scarcely-touching".</p>

<h3>The mechanism: Sun + Moon in line vs. at right angles</h3>
<p>Both the Sun and the Moon raise tides on Earth. When they are
<strong>aligned</strong> with each other and the Earth (full Moon or new
Moon) the two tidal forces add and the range is maximised — these are
<strong>spring tides</strong>. When they pull at <strong>right angles</strong>
(first and last quarter Moon) the forces partly cancel and the range
is minimised — these are <strong>neap tides</strong>.</p>

<p>The cycle from spring to neap and back is about <strong>14.77 days</strong>
— half a lunar month. So in any given calendar month you'll see two
spring tides and two neap tides.</p>

<h3>How big is the difference?</h3>
<p>It depends on the location, but roughly:</p>
<ul>
  <li><strong>Bay of Fundy:</strong> spring range ~16 m, neap range ~11 m.</li>
  <li><strong>English Channel (St Malo):</strong> springs ~12 m, neaps ~5 m.</li>
  <li><strong>North Sea (Hamburg):</strong> springs ~3.8 m, neaps ~3.2 m.</li>
  <li><strong>US East Coast (Boston):</strong> springs ~3.3 m, neaps ~2.4 m.</li>
</ul>

<h3>Why the biggest spring tides come a day or two after full/new Moon</h3>
<p>You'd expect peak spring tide on the exact day of full or new Moon,
but real coasts lag this astronomical signal. The ocean is a big mass
of water and takes time to respond, and the local basin's resonance
adds further delay. This delay is called the <strong>age of the tide</strong>
and is typically 24–48 hours — predictably, day after day. It is
encoded in the phases of the tide's
<a href="/learn/how-predictions-are-made/">harmonic constituents</a>.</p>

<h3>Equinoctial and perigean tides</h3>
<p>Two extras stack on top of the spring/neap cycle:</p>
<ul>
  <li><strong>Equinoctial springs</strong> — around March and September,
  the Sun is in the equatorial plane and its tidal contribution peaks,
  producing the year's largest tides.</li>
  <li><strong>Perigean springs</strong> — when the Moon is at perigee
  (closest to Earth) <em>and</em> aligned with the Sun, the spring tide
  is amplified further. Combined perigean equinoctial springs are the
  highest astronomical tides of any given year.</li>
</ul>
""",
        "related": ["how-tides-work", "largest-tidal-ranges", "tide-types"],
    },

    # ---------- PHENOMENA & RECORDS ----------
    {
        "slug": "largest-tidal-ranges",
        "category": "phenomena",
        "title": "Where are the largest tidal ranges in the world?",
        "summary": "Bay of Fundy, Severn Estuary, Ungava Bay, Río Gallegos — when ocean shape and basin resonance team up, tides can reach 16 metres.",
        "body": """
<p>On the open ocean the tide is barely half a metre high. The
multi-metre ranges we see on the coast are produced by
<strong>basin resonance</strong>: when a bay or estuary has a natural
oscillation period close to 12 h 25 min (the M₂ period), the tidal
wave entering it gets amplified, sometimes spectacularly.</p>

<h3>The top of the leaderboard</h3>
<ol>
  <li><strong>Bay of Fundy, Canada</strong> — up to <strong>16.3 m</strong> at
  Burntcoat Head, Nova Scotia. The bay's length (~270 km) and average
  depth (~75 m) give it a natural period almost exactly 12 hours,
  near-perfect resonance with the semidiurnal tide.</li>
  <li><strong>Ungava Bay, Canada</strong> — rivals Fundy at around
  <strong>15.5 m</strong> in Leaf Basin. The two compete for the world
  record depending on which gauge and which event you measure.</li>
  <li><strong>Severn Estuary, UK</strong> — up to <strong>14 m</strong> near
  Avonmouth and Beachley. The estuary funnels and narrows, concentrating
  the Atlantic tide; it also produces the
  <a href="/learn/tidal-bore/">Severn Bore</a>.</li>
  <li><strong>Río Gallegos, Argentina</strong> — about <strong>13 m</strong>
  on the Patagonian coast. South-American Atlantic tides amplify
  southward along the wide continental shelf.</li>
  <li><strong>Mont-Saint-Michel / Bay of Saint-Malo, France</strong> —
  about <strong>12–13 m</strong>. The bay is famously dangerous; the
  receding tide can leave kilometres of mudflats and then return faster
  than people can walk back.</li>
  <li><strong>Anchorage / Turnagain Arm, Alaska</strong> — about
  <strong>10 m</strong>, also a <a href="/learn/tidal-bore/">bore</a>
  location.</li>
  <li><strong>Inchon, South Korea</strong> — around <strong>9 m</strong>,
  exceptionally large for the Yellow Sea.</li>
</ol>

<h3>Why these places and not others?</h3>
<p>Three ingredients combine to make extreme ranges:</p>
<ul>
  <li><strong>Wide continental shelf</strong> — slows the tidal wave and
  increases its height as it shoals (just like waves at the beach).</li>
  <li><strong>Funnelling geometry</strong> — a converging bay forces the
  same water through a smaller cross-section, raising amplitude.</li>
  <li><strong>Resonance</strong> — the basin's natural period close to
  12 h 25 min produces a near-standing wave that doubles or triples
  the height at the closed end.</li>
</ul>

<h3>What about the smallest?</h3>
<p>Conversely, the <strong>Mediterranean</strong>, <strong>Baltic</strong>, and
the <strong>Caribbean</strong> have tides of only 10–40 cm, because they're
nearly closed off from the open Atlantic. And right at an
<a href="/learn/amphidromic-points/">amphidromic point</a> the tide is
essentially zero.</p>
""",
        "related": ["tidal-bore", "amphidromic-points", "spring-neap-tides"],
    },
    {
        "slug": "tidal-bore",
        "category": "phenomena",
        "title": "What is a tidal bore?",
        "summary": "A wall of water rushing up a river against the current — the world's strangest, surf-able tide.",
        "body": """
<p>A <strong>tidal bore</strong> is a wave that travels <em>upstream</em>
along a river as the rising tide meets the river's downstream flow.
Instead of the water level rising gradually, it arrives as a single
breaking front — a wall of water that can be anywhere from a few
centimetres to <strong>over four metres</strong> tall.</p>

<h3>Where bores happen</h3>
<p>Bores need three things at once:</p>
<ul>
  <li>A <strong>large tidal range</strong> — the bigger the range, the more
  energy in the rising tide.</li>
  <li>A <strong>shallow, gently sloping estuary</strong> — so the tidal
  wave is forced to steepen instead of spreading out.</li>
  <li>A <strong>converging, funnel-shaped channel</strong> — which
  amplifies the front.</li>
</ul>

<h3>The famous bores</h3>
<ul>
  <li><strong>Qiantang Bore, China</strong> — the world's largest, up to
  <strong>4 m high</strong> and travelling at 40 km/h. The bore on the
  Qiantang River near Hangzhou has been observed for 2 000 years; in
  August/September it draws crowds of hundreds of thousands. Some bores
  here are tall enough that surfers ride them for tens of kilometres
  upstream.</li>
  <li><strong>Severn Bore, UK</strong> — up to <strong>2 m</strong>, runs
  up the Severn Estuary on the largest spring tides about 60 times a
  year. The official Environment Agency star-rating system tells you
  how big each one will be. A regular crowd of surfers chases it from
  Awre to Gloucester.</li>
  <li><strong>Petitcodiac Bore (Moncton, Canada)</strong> — historically
  one of North America's largest bores; reduced for years by a
  causeway, mostly restored after the causeway gates were opened in
  2010.</li>
  <li><strong>Pororoca, Amazon</strong> — up to <strong>4 m</strong>,
  travelling 800 km up the river. The Tupi name means "great roar".</li>
  <li><strong>Turnagain Arm Bore, Alaska</strong> — a famous American
  bore, runs the southern arm of Cook Inlet near Anchorage on big
  tides.</li>
  <li><strong>Hooghly Bore, India</strong> — heads up the Hooghly toward
  Kolkata; can be over 2 m on monsoon springs.</li>
</ul>

<h3>The physics</h3>
<p>As the tide enters a shallow, narrowing estuary it is forced to
steepen — the same way an ocean swell breaks at the beach. When the
slope of the leading edge becomes too steep to be supported by the
restoring force of gravity (i.e. its Froude number exceeds 1), it
breaks and propagates as a moving hydraulic jump. The river current
flowing downstream sharpens the contrast: the bore is moving
<em>upstream</em> through water that is moving the other way.</p>

<h3>When to see them</h3>
<p>Always on a <a href="/learn/spring-neap-tides/">spring tide</a> —
ideally a perigean equinoctial spring. Look up the local tide tables,
add the listed time of high water at the river mouth, and the bore
typically arrives at upstream stations a few hours earlier. Local
tourist boards publish bore-watching schedules months in advance.</p>
""",
        "related": ["largest-tidal-ranges", "tidal-currents", "spring-neap-tides"],
    },
    {
        "slug": "amphidromic-points",
        "category": "phenomena",
        "title": "Where is there (almost) no tide?",
        "summary": "Around an amphidromic point the tide rotates rather than rises and falls — and at the centre it barely moves at all.",
        "body": """
<p>If gravity from the Moon raises tides everywhere on Earth, you might
expect every coast to see some semidiurnal rise and fall. But there are
spots in every ocean where the tide is essentially <strong>zero</strong> —
or where the cycle is reduced to a few centimetres while
neighbouring coasts swing 4 m. These are <strong>amphidromic points</strong>.</p>

<h3>What's actually happening</h3>
<p>The tidal wave does not slosh back and forth as a single standing wave;
in any ocean basin it travels as a <strong>rotating Kelvin wave</strong>,
trapped against the coast by the Coriolis force. The wave circulates
around a point — clockwise in the southern hemisphere, anti-clockwise
in the northern. The point at the centre, where the phase lines
converge, is the <strong>amphidromic point</strong>. At that point the
tidal range from the dominant constituent is essentially zero.</p>

<h3>Famous amphidromes</h3>
<ul>
  <li><strong>Southern North Sea</strong> — three amphidromes for M₂,
  one off the Norwegian coast, one in the southern bight (off the
  Dutch / English coast near the Brown Ridge), one off the south coast
  of Norway. They are why Norfolk has small M₂ but big surge risk;
  why the Dutch coast has very different ranges from English coast at
  the same latitude.</li>
  <li><strong>Mediterranean</strong> — at least one M₂ amphidrome south
  of Sicily; Mediterranean tides are tiny because the basin is closed
  off and the residual amphidromic system is weak.</li>
  <li><strong>Gulf of Mexico</strong> — an M₂ amphidrome roughly in the
  middle of the gulf. This is partly why the
  <a href="/learn/tide-types/">Gulf tides are diurnal</a> — the
  semidiurnal component is killed off, leaving the diurnal K₁ to
  dominate.</li>
  <li><strong>South China Sea</strong> — multiple amphidromes, complex
  patchwork of semidiurnal, mixed, and diurnal coasts.</li>
</ul>

<h3>Why "almost" zero</h3>
<p>Each tidal constituent (M₂, S₂, K₁, O₁, …) has its <em>own</em>
amphidromic system, and they don't coincide. Even at a point where M₂
is essentially zero, the smaller constituents typically produce a few
centimetres of residual tide. And the <em>weather tide</em> — storm
surge, atmospheric pressure changes — adds another few decimetres of
variability. The astronomical tide may be near-zero, but the sea
level still changes.</p>

<h3>What this means for sailors</h3>
<p>If you cross a region near an amphidromic point, you may pass within
a few miles from a station with 30 cm tides to one with 3 m tides. The
charts and tidal stream atlases in these regions are particularly
worth consulting — tidal currents can be strong even where the
vertical range is small, because water still has to flow <em>around</em>
the amphidrome.</p>
""",
        "related": ["tide-types", "tidal-currents", "how-tides-work"],
    },
    {
        "slug": "meteotsunamis-seiches",
        "category": "phenomena",
        "title": "Meteotsunamis and seiches — when it's not the tide",
        "summary": "Some sudden water-level changes look tidal but are caused by atmosphere or basin resonance — and predictions can't see them coming.",
        "body": """
<p>Not every rise and fall of the sea is tide-related. Two phenomena
in particular sometimes get blamed on tides — and aren't.</p>

<h3>Seiches</h3>
<p>A <strong>seiche</strong> is a standing wave oscillating back and forth
across a closed or semi-closed basin: a harbour, a lake, a fjord. The
basin has a natural period (typically 5 – 90 minutes for harbours,
hours for lakes), and once it gets set into oscillation — by a passing
storm, an earthquake, or a sudden pressure jump — the water continues
to slosh back and forth for hours.</p>

<ul>
  <li><strong>Lake Geneva</strong>: seiches of up to 1.9 m, period ~73 min.
  Sailors there literally call them "seiches" (Swiss-French origin of
  the term).</li>
  <li><strong>Lake Erie</strong>: storm-driven seiches frequently swing
  the lake's eastern end by 2 m relative to the western end.</li>
  <li><strong>Port harbours</strong> like Ciutadella (Menorca, Spain) and
  Nagasaki suffer recurrent harbour seiches that disrupt
  shipping.</li>
</ul>

<h3>Meteotsunamis</h3>
<p>A <strong>meteotsunami</strong> is a tsunami-like wave produced by
atmospheric pressure jumps — often associated with squall lines or
"derechos" passing over shallow water. The mechanism is the
<strong>Proudman resonance</strong>: if the pressure disturbance moves
across the sea at roughly the speed of long ocean waves
(√(g·h)), it pumps energy into the water continuously. By the time
it reaches a constricted bay it can produce waves several metres high.</p>

<ul>
  <li><strong>Ciutadella, Menorca (Spain)</strong> — the
  <em>Rissaga</em>: meteotsunamis up to 4 m, well known since the 18th
  century.</li>
  <li><strong>Nagasaki Bay, Japan</strong> — the
  <em>Abiki</em>: similar mechanism, up to 5 m in 1979.</li>
  <li><strong>Croatia, Vela Luka 1978</strong> — 6 m meteotsunami caused
  major damage.</li>
  <li><strong>Lake Michigan, USA</strong> — several deadly events
  attributed to meteotsunamis from passing storms.</li>
</ul>

<h3>Storm surges</h3>
<p>Larger and more familiar: a sustained rise in coastal water level due
to wind stress pushing water against the shore and to low atmospheric
pressure raising the sea ("the inverted barometer effect"). A 1 mbar
drop in pressure raises sea level by about 1 cm. The 1953 North Sea
flood, Hurricane Katrina (2005), and Cyclone Sidr (Bangladesh, 2007)
were all storm surge events, where the actual water level was
<em>metres</em> higher than the predicted astronomical tide.</p>

<h3>Why predictions miss them</h3>
<p>Astronomical
<a href="/learn/how-predictions-are-made/">tide prediction</a> uses
only the gravitational forcing. It cannot see weather. A storm surge,
seiche, or meteotsunami arrives on top of the predicted tide — and a
storm at high water can be devastating. See
<a href="/learn/prediction-limits/">what predictions can't do</a>.</p>
""",
        "related": ["prediction-limits", "amphidromic-points", "how-predictions-are-made"],
    },

    # ---------- HOW PREDICTIONS WORK ----------
    {
        "slug": "how-predictions-are-made",
        "category": "predictions",
        "title": "How are tide predictions made?",
        "summary": "Harmonic analysis: a year of measurements turns into ~30–100 sine waves that can predict the tide decades into the future.",
        "body": """
<p>Tide prediction is one of the oldest applications of mathematical
modelling to nature, and one of the most successful. Modern predictions
for a port a year from now are typically accurate to within a few
centimetres — without any input from weather forecasts, satellite data,
or real-time observations.</p>

<h3>The fundamental idea: harmonic analysis</h3>
<p>The tide-raising force at any point on Earth can be decomposed into
a sum of cosines, each at a precisely known astronomical frequency:</p>

<ul>
  <li><strong>M₂</strong> (principal lunar semidiurnal) — period
  12 h 25 min, the largest constituent almost everywhere.</li>
  <li><strong>S₂</strong> (principal solar semidiurnal) — period
  12 h exactly.</li>
  <li><strong>K₁, O₁</strong> — the main diurnal pair, important wherever
  diurnal or mixed tides occur.</li>
  <li><strong>N₂, K₂, P₁, Q₁, …</strong> — smaller constituents that account
  for the Moon's elliptical orbit and other refinements.</li>
  <li>Plus <strong>shallow-water constituents</strong> (M₄, M₆, MS₄, MN₄, …)
  that capture the nonlinear distortion of the tide as it propagates over
  shallow shelves and into estuaries.</li>
</ul>

<p>The total tide at any location is</p>
<pre>h(t) = Z₀ + Σᵢ fᵢ · Aᵢ · cos(σᵢ · t + Vᵢ(t) + uᵢ − Gᵢ)</pre>

<p>where each constituent has a known frequency σᵢ and astronomical
argument Vᵢ(t) + uᵢ, but a station-specific amplitude Aᵢ and phase Gᵢ
to be determined from observations. (The fᵢ and uᵢ are slow "nodal
modulations" that vary with an 18.6-year cycle of the Moon's orbit.)</p>

<h3>Determining the constituents</h3>
<p>Take a year or more of hourly water-level observations from a gauge.
A least-squares fit (today done with software like
<a href="https://github.com/wesleybowman/UTide">UTide</a>) finds the
amplitudes Aᵢ and phases Gᵢ that best reproduce the observations.
Typically 35–70 constituents are fitted; the largest 10–15 carry
most of the variance. The longer the record (ideally one nodal cycle,
18.6 years), the more reliable the constituents.</p>

<h3>From constituents to predictions</h3>
<p>Once you have the constituents, the formula above runs forward in
time as long as you like. The astronomical arguments Vᵢ(t) are
calculated from the positions of Sun and Moon, which are known
centuries ahead. Software like <a href="http://www.flaterco.com/xtide/">XTide</a>
predicts tides for any future date in milliseconds.</p>

<h3>For ports without long records</h3>
<p>A site with only a month of observations isn't long enough to
separate constituents that differ by 1 cycle per month — the M₂ and N₂
pair, for example. Two workarounds:</p>
<ul>
  <li><strong>Reference / subordinate station offsets</strong> — apply
  fixed time and height offsets to a nearby reference station.</li>
  <li><strong>Hydrodynamic models</strong> — interpolate amplitudes and
  phases from large-scale ocean models like FES2014 or TPXO.</li>
</ul>

<p>This site uses thousands of harmonic stations from authoritative
sources (XTide's bundled databases, UHSLC sea-level records, national
hydrographic offices) plus our own UTide analyses where high-quality
records exist.</p>
""",
        "related": ["prediction-limits", "datums-explained", "how-tides-work"],
    },
    {
        "slug": "prediction-limits",
        "category": "predictions",
        "title": "What can tide predictions (not) do?",
        "summary": "The astronomical tide is rock-solid. The actual water level is something else — and there are limits you should know about.",
        "body": """
<p>Tide predictions are remarkable: a few weeks of measurements at a
port produce predictions accurate to centimetres, decades into the
future. But the predicted height is the <strong>astronomical tide
only</strong>. Several things will change the <em>actual</em> water level
on the day.</p>

<h3>What predictions get right</h3>
<ul>
  <li><strong>Timing of high and low water</strong> — usually within
  10 minutes for a year-old prediction at a well-analysed station.</li>
  <li><strong>Tidal range</strong> — typically within a few percent on
  any single tide.</li>
  <li><strong>Spring/neap variability</strong> — the
  <a href="/learn/spring-neap-tides/">14.77-day cycle</a> is dictated
  by the Sun-Moon geometry and is exact.</li>
  <li><strong>Long-term seasonal patterns</strong> — to the extent they
  are encoded in the annual S₂a/SA constituent.</li>
</ul>

<h3>What predictions get wrong (or never see)</h3>
<ul>
  <li><strong>Storm surge.</strong> A strong onshore wind can push the
  water 1 – 5 m above prediction. Hurricane Katrina's surge was
  ~8 m. The 1953 North Sea flood was ~3 m of surge on top of an
  ordinary spring tide.</li>
  <li><strong>Atmospheric pressure.</strong> A 1 hPa drop in barometric
  pressure raises sea level by about 1 cm — the
  "inverted barometer" effect. A typical low-pressure system
  contributes ~10–30 cm.</li>
  <li><strong>Seasonal sea level.</strong> Many coasts swing 10–30 cm
  between summer and winter due to thermal expansion and prevailing
  wind regime. A long enough record (one full year) captures this in
  S<sub>a</sub>; shorter records miss it.</li>
  <li><strong>River discharge.</strong> In estuaries, freshwater flow
  raises the water level several decimetres above prediction during
  spring snowmelt.</li>
  <li><a href="/learn/meteotsunamis-seiches/"><strong>Seiches and
  meteotsunamis.</strong></a> Sudden harbour oscillations of 0.5–4 m,
  unpredictable.</li>
  <li><strong>Tsunamis.</strong> Obviously.</li>
  <li><strong>Local effects.</strong> Construction (jetties,
  reclamation) can change a port's tide significantly; predictions
  based on pre-construction data become biased.</li>
</ul>

<h3>What about wind and waves?</h3>
<p>Astronomical tide predictions tell you nothing about wave height. The
actual water level at your boat or your beach is the predicted tide
plus the surge plus the wave run-up. On exposed coasts, breaking-wave
run-up can raise the effective water level by several metres above the
calm-water tide. Pair tide prediction with a wave/swell forecast for a
full picture.</p>

<h3>Take-home</h3>
<p>The astronomical tide is a deterministic, decades-stable signal.
Treat the predictions as the baseline expected water level under
calm-weather conditions. For any safety-critical activity — navigating
a narrow channel at low water, beaching a vessel, planning a coastal
construction lift — combine tide tables with a real-time gauge and an
up-to-date weather forecast.</p>
""",
        "related": ["how-predictions-are-made", "meteotsunamis-seiches", "datums-explained"],
    },
    {
        "slug": "datums-explained",
        "category": "predictions",
        "title": "MSL, LAT, chart datum — what do the tide-height numbers mean?",
        "summary": "A tide table number is meaningless without its reference level. Here are the four you'll meet on this site.",
        "body": """
<p>A tide table says "high water 3.4 m". 3.4 m above <em>what</em>?
The reference level — the <strong>datum</strong> — is as important as the
number itself. Confuse two datums and you can be metres off.</p>

<h3>The main datums in use</h3>
<ul>
  <li><strong>Mean Sea Level (MSL)</strong> — the long-term average water
  level at a station. Computationally clean, easy to compute from a
  long enough record. Often used by scientific sea-level networks
  (PSMSL, UHSLC).</li>
  <li><strong>Mean Lower Low Water (MLLW)</strong> — the long-term average
  of the lower of the two daily lows. Standard for
  <strong>US</strong> NOAA charts. Heights above MLLW are always
  positive in a normal tide regime.</li>
  <li><strong>Chart Datum (CD)</strong> — a generic term for "the datum
  on the nautical chart". In most non-US countries today, CD is set to
  <strong>LAT</strong> (Lowest Astronomical Tide), but historic charts
  may use older datums like Mean Low Water Springs.</li>
  <li><strong>Lowest Astronomical Tide (LAT)</strong> — the lowest tide
  predicted to occur over a 19-year nodal cycle (assuming average
  meteorology). Adopted by the International Hydrographic Organization
  in 1999; standard chart datum in Europe, Australia, India, much of
  Asia.</li>
  <li><strong>Highest Astronomical Tide (HAT)</strong> — the corresponding
  upper bound. Used for clearance heights under bridges and powerlines.</li>
</ul>

<h3>How they relate</h3>
<p>For a typical NW-European port the spacing is roughly:</p>
<pre>HAT  ~ MSL + tidal amplitude
MHWS ~ MSL + 0.85 × tidal amplitude
MSL  (zero)
MLWS ~ MSL − 0.85 × tidal amplitude
LAT  ~ MSL − tidal amplitude
</pre>
<p>So at a port with 3 m tidal amplitude (6 m range), LAT is ~3 m below
MSL. A "1.0 m above LAT" reading means roughly "2 m below MSL".</p>

<h3>How we handle this on the site</h3>
<p>Each station has its own datum, listed in the <em>Station details</em>
on the prediction page. Where the source provides LAT, we report
heights above LAT. Where the source provides MLLW, we report heights
above MLLW. We do <strong>not</strong> silently convert between datums —
because the offsets are station-specific and not always known.</p>

<h3>Why this matters</h3>
<ul>
  <li><strong>Depth-under-keel:</strong> a chart shows the depth at
  chart datum. A tide table tells you how much water is above chart
  datum at that moment. Add them up.</li>
  <li><strong>Bridge clearance:</strong> a chart shows the air gap at
  HAT. The actual gap at any moment is air-gap + (HAT − current tide
  height).</li>
  <li><strong>Construction levels:</strong> shore defences are designed
  to a return period above HAT; mixing MSL and HAT is a serious error.</li>
</ul>

<p>If you take only one thing from this article: when you read a tide
height, always check the datum. The number alone tells you only the
amount of water in the same units used on the same chart, not the
absolute level.</p>
""",
        "related": ["how-predictions-are-made", "prediction-limits", "spring-neap-tides"],
    },

    # ---------- CURRENTS ----------
    {
        "slug": "tidal-currents",
        "category": "currents",
        "title": "How do tidal currents form?",
        "summary": "The tide is a wave. Water has to flow somewhere to make it rise and fall — that flow is the tidal current.",
        "body": """
<p>The vertical rise and fall of the tide is only half the story. As
the water level changes, water has to be <em>delivered</em> into the
basin and then <em>removed</em>; that motion is the
<strong>tidal current</strong>. It can run at a few centimetres per
second in the open ocean and at over 8 m/s (16 kn) in narrow channels.</p>

<h3>Standing tide vs. progressive tide</h3>
<p>Whether high water coincides with maximum current depends on the
type of tidal wave:</p>
<ul>
  <li><strong>Standing wave</strong> (in a closed-end basin like the
  Bay of Fundy): maximum current is at <strong>mid-tide</strong>; current
  is zero ("slack water") at high and low water.</li>
  <li><strong>Progressive wave</strong> (in an open channel like the
  English Channel): maximum current is roughly <strong>at high water</strong>
  and minimum at low water — flood and ebb are 6 hours each rather
  than offset by 3.</li>
</ul>
<p>Real coasts are a mix of the two. The phase relationship between
height and current is something a station-specific harmonic analysis
captures explicitly.</p>

<h3>Tidal-stream constituents</h3>
<p>Just like sea level, currents can be decomposed into harmonic
constituents M₂, S₂, K₁, … — but for currents, each constituent is a
<strong>vector</strong> (a tidal ellipse) rather than a scalar. The
ellipse describes:</p>
<ul>
  <li>the major and minor axes (peak speed and "cross-flow" speed)</li>
  <li>the orientation of the major axis (the dominant flood/ebb
  direction)</li>
  <li>the sense of rotation (clockwise or anti-clockwise)</li>
  <li>the phase of peak flow.</li>
</ul>
<p>In a narrow channel the ellipse degenerates almost to a line — the
current just reverses. In open shelf water it can be a fat ellipse,
with the current rotating continuously.</p>

<h3>Flood, ebb, slack</h3>
<ul>
  <li><strong>Flood:</strong> incoming current, generally toward the
  coast / up the estuary.</li>
  <li><strong>Ebb:</strong> outgoing current.</li>
  <li><strong>Slack water:</strong> the brief period of near-zero
  current between flood and ebb.</li>
</ul>
<p>"Slack water" is when divers, scullers, and small craft prefer to
move. It can last only a few minutes in a powerful narrows.</p>

<h3>Eddies and overfalls</h3>
<p>Where strong tidal currents meet headlands, banks, or other currents,
they produce <strong>eddies</strong> (rotating water masses, sometimes
permanent in a tidal cycle) and <strong>overfalls</strong> (steep,
breaking water with strong vertical motion). These can be hazardous to
small craft even in flat weather.</p>

<h3>What we predict</h3>
<p>Our <em>current</em> stations show predicted current speeds and
directions in much the same form as the tide curves — peaks of flood
and ebb instead of high and low water. Where a station appears on our
map with a current arrow, we have either a published harmonic current
station or a derivation from a nearby tide gauge with known phase
offsets. See
<a href="/learn/strongest-currents/">strongest tidal currents</a> for
record-holders.</p>
""",
        "related": ["strongest-currents", "why-currents-matter", "tidal-bore"],
    },
    {
        "slug": "strongest-currents",
        "category": "currents",
        "title": "Where are the world's strongest tidal currents?",
        "summary": "Saltstraumen, Skookumchuck, Naruto, Pentland Firth — when the tide flows through a small gap, the water has to hurry.",
        "body": """
<p>To produce a violent tidal current you need a large tidal range on
one side of a narrow constriction, and a smaller range on the other —
the level difference drives the flow. The biggest pinch-points reach
truly remarkable speeds.</p>

<h3>The headline list</h3>
<ol>
  <li><strong>Saltstraumen, Norway</strong> — peak ~<strong>22 kn</strong>
  (40 km/h). A 3-km-long, 150-m-wide channel between Saltfjorden and
  Skjerstadfjorden; on big tides, around 400 million m³ of water moves
  through in 6 hours. Giant whirlpools (max 10 m across) form near
  peak flow.</li>
  <li><strong>Moskstraumen, Lofoten, Norway</strong> — peak
  ~<strong>11 kn</strong>. The original "Maelstrom" — gave its name to
  the English word. Less violent than Saltstraumen but more famous
  thanks to Poe and Verne.</li>
  <li><strong>Naruto Strait, Japan</strong> — peak
  ~<strong>11 kn</strong>. Between Honshu and Shikoku; famous whirlpools
  (Naruto no Uzushio) reach 20 m across on big springs, viewable from
  the Naruto Bridge.</li>
  <li><strong>Skookumchuck Narrows, BC, Canada</strong> — peak
  ~<strong>16 kn</strong>. Sechelt Inlet drains through a kilometre-wide
  bottleneck. Standing waves and overfalls draw whitewater kayakers
  from around the world.</li>
  <li><strong>Pentland Firth, Scotland</strong> — peak
  ~<strong>12 kn</strong>. The strait between mainland Scotland and the
  Orkneys; a major shipping route despite the violent currents.
  Tidal-energy turbines (MeyGen) are deployed there.</li>
  <li><strong>Corryvreckan, Scotland</strong> — peak
  ~<strong>8.5 kn</strong>. A narrow gulf between the Inner Hebridean
  islands of Jura and Scarba; the world's third-largest natural
  whirlpool, with permanent standing waves and roaring overfalls.</li>
  <li><strong>Old Sow, Bay of Fundy</strong> — peak
  ~<strong>10 kn</strong>. North America's largest whirlpool, in the
  outer Bay of Fundy.</li>
  <li><strong>Cape Race / Cape St Vincent / various Cape passages</strong>
  — locally 4–8 kn around major capes where currents accelerate
  around the headland.</li>
</ol>

<h3>Why narrows are so fast</h3>
<p>Conservation of mass requires that volume flow be the same on either
side of a narrows: V·A = const. If the cross-section shrinks by a
factor 10, the velocity rises by a factor 10. The narrowest passages
of the Pentland Firth or Saltstraumen are 10 m deep and 100 m wide
serving fjords 100 km long — that's a velocity multiplier of
roughly 100.</p>

<h3>Slack water</h3>
<p>Even in the most violent passages, there are slack-water windows
between flood and ebb. In Saltstraumen the slack lasts about 20
minutes around the predicted turn; in less extreme narrows it may last
an hour. Tourist boats, scuba divers, and prudent skippers all plan
their passages around the predicted slack — and a good
<a href="/learn/how-predictions-are-made/">current prediction</a> is
exactly what they consult.</p>

<h3>Forces beyond the tide</h3>
<p>Strong currents elsewhere — the Gulf Stream, the Agulhas, the
Antarctic Circumpolar Current — are not tidal but driven by wind and
density. Tidal currents are local, predictable, and reversing. They
are also the only ones that produce coherent
<a href="/learn/tidal-bore/">bores</a>.</p>
""",
        "related": ["tidal-currents", "why-currents-matter", "tidal-bore"],
    },
    {
        "slug": "why-currents-matter",
        "category": "currents",
        "title": "Why are current forecasts important, and for whom?",
        "summary": "Anyone whose plans depend on the direction or speed of water needs to know what the current will do.",
        "body": """
<p>Tidal current information is less famous than tide tables but
equally consequential. For some users it's a comfort issue; for others
it's a safety-of-life matter.</p>

<h3>Sailors and motor-boaters</h3>
<p>A 3-knot foul current on a 5-knot sailing boat turns a one-hour
passage into a two-hour one. Skippers transiting tide-dominated waters
(English Channel, Solent, San Francisco Bay, Strait of Belle Isle,
Bass Strait) routinely time their departures by the current rather
than by the wind. Many cruising guides print current charts at hourly
intervals — they exist because someone realised the boat won't get
home before sunset otherwise.</p>

<h3>Sea kayakers and rowers</h3>
<p>For human-powered craft, paddling against 2 kn of tidal current is
back-breaking; with it, exhilarating. Kayakers crossing tidal channels
(Menai Strait, Bay of Fundy, San Juan Islands, Lofoten) plan around
slack water — anything else is dangerous.</p>

<h3>Scuba divers</h3>
<p>Dive sites in tide-affected waters (Scapa Flow, Sechelt, Cape Cornwall,
Channel Islands) can be dived only at slack water. The published
prediction times are the gospel of dive briefings.</p>

<h3>Ferries, ships, harbour pilots</h3>
<p>Large vessels manoeuvring in restricted waters must account for
current set. Pilots in places like the Elbe, the Thames, the
St Lawrence, or the Hong Kong approaches use real-time current
information layered on top of the predicted tide.</p>

<h3>Fishermen — both commercial and recreational</h3>
<p>Fish concentrate where currents do — at headlands, slack-water
edges, current-shear zones. Anglers fish the change of tide; trawlers
plan tow direction by it. In places like the Bay of Fundy, the
scallop and lobster industries can only work the bottom at slack.</p>

<h3>Tidal energy operators</h3>
<p>Tidal stream generators (MeyGen at Pentland Firth, La Rance dam in
France, projects in Bay of Fundy) base their power forecasts on tidal
current predictions. Energy yield is roughly proportional to v³, so a
small error in predicted current speed produces a large error in
expected power output.</p>

<h3>Coastal engineers and oceanographers</h3>
<p>Sediment transport, beach evolution, dispersion of contaminants,
search-and-rescue drift modelling — all start with the local current
field. Tidal currents typically dominate over wind-driven and density-
driven flows in shallow shelf seas.</p>

<h3>The take-home</h3>
<p>If your activity depends on water moving in a particular direction
at a particular speed, or on it being still at a particular moment,
you need a tidal current forecast. The major
<a href="/learn/strongest-currents/">tide-current passages</a> of the
world are mapped to within minutes — use the data, don't fight it.</p>
""",
        "related": ["tidal-currents", "strongest-currents", "why-predictions-matter"],
    },

    # ---------- PRACTICE ----------
    {
        "slug": "why-predictions-matter",
        "category": "practice",
        "title": "Why are tide predictions important, and for whom?",
        "summary": "Shipping, beach-going, harbour engineering, emergency management — almost everyone with a coastline relies on tide tables.",
        "body": """
<p>The tide tables started as commercial documents — the first English
tide tables were sold to London ship masters in the 13th century.
Today, tide prediction underpins billions of dollars of activity every
day, and saves countless lives every year.</p>

<h3>Commercial shipping</h3>
<p>Many of the world's largest ports — Rotterdam, Hamburg, Antwerp,
Felixstowe, Shanghai, New York — sit at the head of tidal estuaries.
Container ships and tankers must arrive at the port entrance on the
right tide; the depth in approach channels at low water is sometimes
only enough for empty barges. Pilot bookings, lock cycles, and ship
schedules are all coordinated around predicted tides. A 5-minute
error in the predicted time of HW can cost a ship its tide window.</p>

<h3>Naval and military operations</h3>
<p>D-Day on 6 June 1944 was scheduled around the predicted tide and
moon: assault forces needed a rising tide at dawn with the
obstacles still visible. Today, amphibious operations, mine clearance,
submarine operations, and beach landings all consult tide tables in
mission planning.</p>

<h3>Beach safety and tourism</h3>
<p>Tidal flats kill people every year — Morecambe Bay, Mont-Saint-Michel,
the German Wadden Sea. People walk out on bare sand and the rising tide
returns faster than they can return. Public lifeguard services, beach
authorities, and walking-tour operators rely on accurate tide tables
to manage access.</p>

<h3>Coastal engineering and construction</h3>
<p>Building anything on, in, or under the water — piers, sea defences,
offshore wind turbines, submarine cables — requires accurate prediction
of tidal windows. Heavy-lift cranes and barges can only work at
particular tide states. Pile-driving at the wrong tide can lose
expensive equipment.</p>

<h3>Emergency management and flood warning</h3>
<p>Storm-surge forecasts are computed as <em>residual</em> above the
predicted tide. The decision to issue a flood warning, evacuate coastal
neighbourhoods, or close flood barriers (Thames Barrier, MOSE in Venice,
Maeslantkering in the Netherlands, Eider Barrage) is taken when the
predicted tide + forecast surge approaches a critical threshold.</p>

<h3>Fishing, aquaculture, and shellfish</h3>
<p>Oyster and mussel farmers work the intertidal zone — accessible only
on the low tide. The same goes for kelp harvest, abalone diving, and
hand-gathered shellfish in many coastal communities worldwide.</p>

<h3>Surfing and recreation</h3>
<p>Many surf spots break only at particular tide states — too high and
the wave doesn't break, too low and the rocks are exposed. The
combination of swell forecast and tide table is the basic toolkit of
the surfing world.</p>

<h3>The breadth of users</h3>
<p>The tide affects everyone with a connection to the coast: from
commercial deep-sea shipping to a family walking the dog. The reason
tide predictions are a free public good in most countries is that the
benefits are far too widely distributed to capture commercially —
they go to almost everyone in a coastal economy.</p>
""",
        "related": ["why-currents-matter", "how-predictions-are-made", "prediction-limits"],
    },
    {
        "slug": "reading-a-tide-curve",
        "category": "practice",
        "title": "How do I read a tide curve and table?",
        "summary": "A quick tour of the prediction page: high/low water, range, datum, slack water and the rule of twelfths.",
        "body": """
<p>Every <a href="/">prediction page</a> on this site shows two things:
a 7-day <strong>curve</strong> (graphic) and a 7-day <strong>table</strong>
of the same predictions in numeric form. Here's how to read them
quickly.</p>

<h3>The curve</h3>
<p>Time runs along the horizontal axis, height above the local
<a href="/learn/datums-explained/">datum</a> along the vertical axis.
The grey/blue waving line is the predicted water level. Peaks are
high waters (HW), troughs are low waters (LW). Vertical light/dark
banding indicates day vs. night.</p>

<p>Things to look at in the curve:</p>
<ul>
  <li>How <strong>symmetric</strong> are HW and LW peaks? Symmetric
  curves indicate a standing-wave-dominated regime; asymmetric
  (steeper rise than fall, or vice versa) indicates shallow-water
  effects.</li>
  <li>Is the <strong>range</strong> growing or shrinking across the week?
  Growing range over 4 days → approaching springs. Shrinking →
  approaching neaps.</li>
  <li>Are <strong>two adjacent HWs of similar size</strong>, or are some
  visibly smaller? That tells you the tide type:
  <a href="/learn/tide-types/">semidiurnal, mixed, or diurnal</a>.</li>
</ul>

<h3>The table</h3>
<p>Each row is one tide event:</p>
<ul>
  <li><strong>Date</strong> (first event of the day) and <strong>time</strong>
  in the timezone chosen at the top of the page.</li>
  <li>An <strong>icon</strong> — ▲ rising, ▼ falling, ◐ moonrise, etc.</li>
  <li>The <strong>event type</strong>: High Tide, Low Tide, sometimes
  Moonrise/Moonset or astronomical events.</li>
  <li>The <strong>height</strong> above the station's datum.</li>
</ul>

<h3>The rule of twelfths (a quick approximation)</h3>
<p>For a semidiurnal tide with roughly 6 hours between LW and HW,
useful for mental arithmetic:</p>
<ul>
  <li>1st hour: 1/12 of the range rises</li>
  <li>2nd hour: 2/12</li>
  <li>3rd hour: 3/12</li>
  <li>4th hour: 3/12</li>
  <li>5th hour: 2/12</li>
  <li>6th hour: 1/12</li>
</ul>
<p>So in the middle two hours, half the total rise (or fall) happens.
This is why mudflats fill so quickly mid-tide.</p>

<h3>Picking the right station</h3>
<p>The closer the station is to where you actually are, the better the
prediction. In a tidal estuary or river, even a few kilometres up- or
down-stream can shift HW by 15–30 minutes and change the range by
metres. The prediction page lists
<a href="/">nearby stations</a> at the bottom — if your spot of
interest is on a different reach of the estuary, one of those may be a
better match than the closest geographic station.</p>

<h3>Local vs. UTC</h3>
<p>The "Times" toggle at the top of the page switches between
<strong>local civil time</strong> at the station (typically the country's
official timezone, including DST changes) and <strong>UTC</strong>. UTC
is useful for coordinating across timezones (e.g. comparing
predictions for ports on opposite shores) and for matching against
weather model timestamps.</p>
""",
        "related": ["datums-explained", "tide-types", "how-predictions-are-made"],
    },
]


SLUG_INDEX = {a["slug"]: a for a in ARTICLES}
ARTICLES_BY_CATEGORY = {cat_id: [] for cat_id, _ in CATEGORIES}
for a in ARTICLES:
    ARTICLES_BY_CATEGORY[a["category"]].append(a)
