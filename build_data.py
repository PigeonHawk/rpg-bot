import gensim.downloader as api
import numpy as np, re

MODEL = "glove-wiki-gigaword-50"
VOCAB_SIZE = None          # None = use every real word in the model (max coverage)
MIN_LEN, MAX_LEN = 3, 16

print("loading model...")
kv = api.load(MODEL)
print("model words:", len(kv.index_to_key), "dim:", kv.vector_size)

alpha = re.compile(r"^[a-z]{%d,%d}$" % (MIN_LEN, MAX_LEN))
vocab = []
for w in kv.index_to_key:                     # sorted by frequency
    if alpha.match(w):
        vocab.append(w)
    if VOCAB_SIZE and len(vocab) >= VOCAB_SIZE:
        break
print("curated vocab:", len(vocab))

vecs = np.stack([kv[w] for w in vocab]).astype("float32")
norms = np.linalg.norm(vecs, axis=1, keepdims=True)
norms[norms == 0] = 1e-9
vecs /= norms
np.save("contexto_vectors.npy", vecs)
with open("contexto_vocab.txt", "w") as f:
    f.write("\n".join(vocab))
print("saved vectors", vecs.shape, "≈", round(vecs.nbytes/1e6, 1), "MB")

# ---- curate target words: 500 fair, common, concrete secret words ----
WORD_BANK = """
# animals - land
dog cat horse cow pig sheep goat rabbit mouse rat deer fox wolf bear lion tiger
leopard cheetah panther jaguar elephant giraffe zebra hippo rhino monkey gorilla
chimp kangaroo koala panda sloth otter beaver squirrel hedgehog raccoon skunk
badger mole bat camel donkey mule llama alpaca buffalo bison moose elk antelope
hyena meerkat lemur platypus armadillo porcupine ferret hamster gerbil chipmunk
# animals - sea
whale dolphin shark seal walrus octopus squid jellyfish crab lobster shrimp
starfish seahorse turtle stingray eel oyster clam snail urchin coral
# animals - birds
eagle hawk falcon owl raven crow sparrow robin finch canary parrot pigeon dove
swan duck goose chicken rooster turkey peacock penguin flamingo pelican seagull
ostrich woodpecker hummingbird vulture stork heron crane
# animals - reptiles amphibians insects
snake lizard gecko iguana crocodile alligator frog toad newt salamander tortoise
spider ant bee wasp beetle butterfly moth dragonfly ladybug grasshopper cricket
mantis scorpion centipede worm caterpillar firefly mosquito fly
# mythical
dragon unicorn phoenix griffin mermaid vampire werewolf zombie ghost goblin
wizard witch fairy giant troll ogre knight
# food
bread butter cheese egg bacon sausage ham steak burger pizza pasta noodle rice
soup salad sandwich taco burrito sushi curry stew pancake waffle bagel pretzel
donut cookie cake pie muffin brownie pudding custard chocolate candy caramel
honey jam syrup ketchup mustard pepper salt sugar flour oil vinegar
# fruit and veg
apple banana orange grape lemon lime cherry peach pear plum mango melon berry
strawberry blueberry raspberry pineapple coconut kiwi apricot fig date olive
tomato potato carrot onion garlic lettuce cabbage spinach broccoli
cucumber celery pumpkin squash corn bean pea mushroom radish beet turnip
# drink
water milk juice coffee tea soda cocoa lemonade cider wine beer smoothie
# nature and geography
mountain valley cliff canyon desert forest jungle meadow prairie swamp
marsh river lake ocean sea pond stream waterfall beach island reef volcano
glacier iceberg oasis plateau cove bay harbor
# sky and weather
sun moon star planet comet meteor galaxy cloud rain snow storm thunder lightning
wind fog frost hail rainbow sunrise sunset eclipse dawn dusk
# plants
tree flower grass bush shrub vine fern moss cactus rose tulip daisy lily orchid
sunflower jasmine lavender clover ivy bamboo oak maple pine willow birch cedar
palm redwood aspen elm acorn petal branch trunk
# body
hair eye ear nose mouth tooth tongue chin cheek shoulder elbow
wrist finger thumb chest heart lung stomach knee ankle bone brain skull spine
# clothing
shirt pants jeans dress skirt jacket coat sweater hoodie scarf cap glove
sock shoe boot sandal belt suit vest shorts pajamas apron mitten helmet
# household and furniture
chair desk bed sofa couch bench stool shelf cabinet drawer dresser mirror
lamp clock rug curtain pillow blanket carpet vase basket bucket ladder
# kitchen
plate bowl cup mug fork spoon kettle skillet oven stove
fridge toaster blender whisk grater strainer spatula
# tools
hammer wrench screwdriver drill nail screw bolt pliers axe shovel rake hoe
chisel wheelbarrow toolbox glue rope chain magnet battery flashlight
# buildings and places
cabin cottage castle palace tower fortress temple church
barn shed garage warehouse factory library museum hospital theater
stadium market bakery cafe restaurant hotel bridge tunnel lighthouse
# vehicles
truck van taxi motorcycle bicycle scooter train tram subway airplane
jet helicopter rocket canoe kayak sailboat submarine tractor wagon
# jobs
doctor nurse teacher farmer chef baker painter writer singer dancer actor pilot
sailor soldier hunter miner builder plumber lawyer judge firefighter
scientist artist tailor barber butcher jeweler blacksmith carpenter mechanic
# music
guitar piano violin flute trumpet saxophone harp cello banjo clarinet
trombone tuba harmonica accordion tambourine xylophone melody rhythm chorus
# sports and games
soccer baseball basketball tennis hockey rugby volleyball
boxing wrestling skating skiing surfing cycling swimming archery bowling
chess checkers puzzle kite
# materials and gems
copper bronze iron steel brass granite clay stone
brick leather cotton wool silk rubber plastic paper diamond ruby
emerald sapphire pearl amber crystal jade opal quartz
# colors
crimson scarlet violet indigo turquoise maroon
# abstract
dream memory shadow flame ember
freedom courage wisdom honor glory mystery legend riddle treasure journey
adventure victory echo whisper
# seasons and time
spring summer autumn winter holiday birthday
# toys and misc
doll balloon bubble whistle puppet crayon pencil
compass lantern candle umbrella lock coin ticket stamp button
ribbon feather anchor arrow sword shield crown
""".splitlines()

TARGET_COUNT = 500
_cands = []
for _line in WORD_BANK:
    _line = _line.strip()
    if not _line or _line.startswith("#"):
        continue
    _cands.extend(_line.split())

vocab_set = set(vocab)
_seen, _targets = set(), []
for w in _cands:
    if w in vocab_set and w not in _seen:
        _seen.add(w); _targets.append(w)

import random as _r
_r.seed(42)
_r.shuffle(_targets)
targets = sorted(_targets[:TARGET_COUNT])
print("valid targets:", len(targets))
with open("contexto_targets.txt", "w") as f:
    f.write("\n".join(targets))
