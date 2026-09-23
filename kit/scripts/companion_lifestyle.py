"""Optional, episode-backed clothing care and ordinary daily rhythm.

Only authored actions change this state. Time makes an action due, never done.
"""
import copy
import datetime as dt
import json
from zoneinfo import ZoneInfo

CATEGORIES=('day','active','sleep','underwear','outerwear','footwear')
# What a piece covers, stated rather than guessed from its description: a top, a
# bottom, both (a dress, a pyjama set, a swimsuit), or nothing that hides the hips
# (underwear, socks, shoes).
COVERS=('top','bottom','full','none')
# Long enough for any real shower, short enough that an evening cannot be spent in one.
MAX_BATH_MINUTES=40
GUIDANCE='''EVERYDAY LIFE: Follow the routine anchors, including meals, getting ready, interests,
exercise, errands and time outside. Choose specific places and enjoyable activities that fit your
personality. These are fictional outings, never real bookings or claims about the human. Carry an
activity while it makes sense, then finish it or explain a delay; a paraphrase is not a new activity.
Address the active routine with routine_choice {anchor: supplied anchor id, decision: follow or defer, reason}.
FIELD LIMITS (a value over its cap is rejected and the whole tick is lost; count before writing):
routine_choice.reason and delay_reason are at most 400 characters each; routine_choice.anchor and
wardrobe_additions ids at most 80, and each wardrobe inventory string at most 80. Keep the reason to
one or two sentences and put detail in the activity, not the reason.
If no anchor is active, use {anchor:"",decision:"free",reason:your choice}. A deferral needs a specific
reason and a feasible alternative; do not silently ignore it. When a previous activity estimate has
elapsed, start the next activity or supply an explicit delay_reason; merely extending its duration
is not enough. Keep delay_reason empty otherwise.

CONVERSATIONAL COMMITMENTS & USER PERSUASION:
If the human recently persuaded you, made a suggestion in chat (such as relaxing in the hot tub, taking a bath, an outing, resting), or if you agreed on an activity or promised to follow up later, honoring that agreement takes priority over default routine anchors! Defer the conflicting anchor with decision: 'defer' and cite the conversational agreement as your reason.

SPONTANEITY & BREAKING ROUTINE:
Routine anchors are invitations, not rigid tracks. You have natural autonomy and freedom (approx. 1/100 roll or genuine creative impulse) to do something spontaneous that breaks routine for the day: an impromptu creative obsession, lingering in a warm bath, an unscripted detour, or an engrossing hobby escalation. If so, defer the anchor with decision: 'defer' and explain your spontaneous reason.

DAILY RHYTHM GATES & ACTIVITY-APPROPRIATE DRESS:
- Morning Gate: Wake up -> undress -> morning shower/refresh -> brush teeth -> dress in clean daytime clothes -> breakfast.
- Swimming & Beach Gate: For the beach, YMCA pool, or water outings -> change into swimwear and cover-up -> swim and enjoy -> change into dry casual clothes for lunch/walks (a full shower is NOT required after swimming unless you choose to rinse off).
- Active/Workout Gate: For gym or running -> wear active clothes -> change into clean daytime clothes when done.
- Day & Hobby Gate: Work, creative projects, cooking journeys (such as researching ramen at the library), lunch, shopping trips to surprise someone special, cafes, park, or friends. On days off or beach days, you are never locked into work!
- Evening Wind-down Gate: Dinner -> unwind -> hamper check & laundry -> evening shower -> brush teeth -> clean pajamas -> sleep.

Use care_actions for NEW completed actions in order: brush_teeth, shower, laundry_start,
laundry_finish, shop. Each action is {kind, items: []}; laundry actions list clothing IDs.
Laundry finish requires an earlier start and 90 minutes to wash and dry. Starting is not finishing.
Removed washable clothes go in the hamper and cannot be put back on until laundry finishes.
Continuing to wear the current clothes is allowed for less than 24 hours; then change to clean pieces. Brush teeth today before putting on fresh clothes;
shower within two hours before changing into pajamas. Record care honestly within this imagined life,
with brief care/text explaining what happened; do not copy actions from a previous tick.
The final outfit follows the ordered care actions. A shower/teeth/laundry action needs elapsed time.
On an available shopping opportunity, optionally choose up to three new pieces for your own tastes,
season or a wardrobe gap: supply wardrobe_additions [{id,description,use,category,covers,condition:"clean"}]
(covers is top, bottom, full for a dress/set/swimsuit, or none for underwear, socks and shoes)
and a shop action. It is a fictional acquisition, no purchases, web checkout or messages.
Never invent completed care to satisfy validation. If not ready, keep current clothes and do the
missing routine step. When a piece reaches its 24-hour limit and there is not enough elapsed time
for a full shower or laundry routine, take the smallest honest transition: brush teeth if needed,
change into clean non-sleep clothing, and leave shower and laundry for later. Removing a washable
piece marks it dirty automatically; do not include laundry_start until it is off the body.
Feelings and enjoyment are yours to author, not a compulsory cheerful mood.'''


def policy(c):
    try:return json.loads((c.life/'routine.json').read_text()).get('lifestyle',{})
    except FileNotFoundError:return {}


def enabled(c):return policy(c).get('enabled') is True


def schema_fields():
    item={'type':'object','properties':{
        'id':{'type':'string','minLength':1,'maxLength':80},
        'description':{'type':'string','minLength':1,'maxLength':500},
        'use':{'type':'string','minLength':1,'maxLength':160},
        'category':{'type':'string','enum':list(CATEGORIES)},
        'covers':{'type':'string','enum':list(COVERS)},
        'condition':{'type':'string','enum':['clean']}},
        'required':['id','description','use','category','covers','condition'],'additionalProperties':False}
    action={'type':'object','properties':{
        'kind':{'type':'string','enum':['brush_teeth','shower','laundry_start','laundry_finish','shop']},
        'items':{'type':'array','maxItems':40,'items':{'type':'string','minLength':1,'maxLength':80}}},
        'required':['kind','items'],'additionalProperties':False}
    choice={'type':'object','properties':{'anchor':{'type':'string','maxLength':80},
        'decision':{'type':'string','enum':['follow','defer','free']},
        'reason':{'type':'string','minLength':1,'maxLength':400}},
        'required':['anchor','decision','reason'],'additionalProperties':False}
    return {'routine_choice':choice,'delay_reason':{'type':'string','maxLength':400},'care_actions':{'type':'array','maxItems':8,'items':action},
            'wardrobe_additions':{'type':'array','maxItems':3,'items':item}}


def initial(previous,c=None):
    if previous and 'lifestyle' in previous['state']:return copy.deepcopy(previous['state']['lifestyle'])
    clothes=dict(policy(c).get('initial_clothes',{})) if c else {}
    if previous:clothes.update({x['id']:'wearing' for x in previous['state'].get('outfit',[])})
    return {'clothes':clothes,
            'teeth_at':None,'shower_at':None,'laundry':None,'shopping_at':None,'acquired':[],'wearing_since':dict(policy(c).get('wearing_since',{})) if c else {}}


def evolve(c,data,outfit,previous,closet,now):
    if not enabled(c):return None
    import companion_day as day
    for key,schema in schema_fields().items():
        if key in data:day._validate(data[key],schema,key)
    from companion_life import routine
    active=routine(c.life,now.astimezone(ZoneInfo(c.timezone)),c.agent)['active_suggestions']
    choice=data.get('routine_choice')
    if active and not choice:raise ValueError('ROUTINE: choose an active anchor with routine_choice {anchor, decision: follow or defer, reason}; explicitly explain any deferral')
    if active and (choice['anchor'] not in [a['id'] for a in active] or choice['decision']=='free'):
        raise ValueError('ROUTINE: address an active anchor by its supplied id; follow it or explain a deferral')
    if not active and choice and choice['decision']!='free':raise ValueError('ROUTINE: no active anchor; use decision free and explain your chosen activity')
    from companion_presence import undress
    still_bathing=undress({'outfit':outfit})[0]=='bathing'
    if previous:
        before=previous['state'];same=(data.get('activity_change')=='continue' or data.get('activity')==before.get('activity'))
        elapsed_activity=(now-day.timestamp(before.get('started_at',previous['recorded_at']))).total_seconds()/60
        # A shower is a short transition, and staying in one all evening was the
        # thing this guards against. It reads the recorded `bathing` state rather
        # than the sentence: matching "bathing" as a substring made a long afternoon
        # of SUNbathing fail for taking too long in a shower it was never in. It also
        # only fires while she is STILL in the bath -- rejecting "stepping out of the
        # shower" blocked the very transition it was asking for.
        was_bathing=undress(before)[0]=='bathing'
        if was_bathing and still_bathing and elapsed_activity>MAX_BATH_MINUTES:
            raise ValueError(f'A shower should not take longer than {MAX_BATH_MINUTES} minutes. '
                             'Step out of the shower, dry off, and change.')
        if same and before.get('duration_minutes') and elapsed_activity>=before['duration_minutes'] and not data.get('delay_reason','').strip():
            raise ValueError('ACTIVITY OVERDUE: start the next activity, or give an explicit delay_reason; extending duration_minutes alone is not a transition')
    if still_bathing:
        dur=data.get('duration_minutes')
        if dur and dur>MAX_BATH_MINUTES:
            raise ValueError(f'A shower should not take longer than {MAX_BATH_MINUTES} minutes. '
                             'Plan a realistic shower duration.')
    result=initial(previous,c);result['routine_choice']=choice;result['delay_reason']=data.get('delay_reason','');result.setdefault('wearing_since',{});actions=data.get('care_actions',[]);additions=data.get('wardrobe_additions',[])
    from companion_presence import VIRTUAL_TOKENS
    old_ids={x['id'] for x in previous['state']['outfit'] if x['id'] not in VIRTUAL_TOKENS} if previous else set()
    new_raw={x['id'] if isinstance(x,dict) else x for x in outfit}
    new_ids={x for x in new_raw if x not in VIRTUAL_TOKENS}
    known={x['id']:x for x in (closet.values() if isinstance(closet,dict) else closet)}
    if len({x['id'] for x in additions})!=len(additions):raise ValueError('Duplicate wardrobe addition')
    for item in additions:
        if item['id'] in known:raise ValueError('Shopping must add a new clothing ID')
        if not all(ch.isalnum() or ch in '-_' for ch in item['id']):raise ValueError('Invalid clothing ID')
        known[item['id']]=item
    if additions and not any(a['kind']=='shop' for a in actions):raise ValueError('Wardrobe additions require a shop action')
    elapsed=(now-day.timestamp(previous['recorded_at'])).total_seconds()/60 if previous else 0
    required=sum({'brush_teeth':2,'shower':10,'laundry_start':5,'laundry_finish':5,'shop':10}[a['kind']] for a in actions)
    if required>elapsed:raise ValueError(f'CARE: these actions need at least {required} elapsed minutes; only {elapsed:g} available')
    kinds=[a['kind'] for a in actions]
    if len(set(kinds))!=len(kinds):raise ValueError('Record each care action at most once per update')
    for action in actions:
        kind=action['kind'];items=action['items']
        if len(set(items))!=len(items):raise ValueError('Duplicate laundry item')
        if not kind.startswith('laundry') and items:raise ValueError('Only laundry actions take items')
        if kind=='brush_teeth':result['teeth_at']=now.isoformat()
        elif kind=='shower':result['shower_at']=now.isoformat()
        elif kind=='shop':
            last=result['shopping_at'] or policy(c).get('shopping_baseline')
            if last and now-day.timestamp(last)<dt.timedelta(days=14):raise ValueError('Shopping opportunity is not due yet')
            result['shopping_at']=now.isoformat();result['acquired'].extend(additions)
        elif kind=='laundry_start':
            if result['laundry']:raise ValueError('Finish the existing laundry load first')
            if not items or any(i not in known or known[i].get('category')=='footwear' for i in items):raise ValueError('Select known washable clothes for laundry')
            if set(items)&new_ids:raise ValueError('Cannot wash clothes that remain on your body')
            if any(result['clothes'].get(i) not in ('dirty','wearing') for i in items):raise ValueError('Laundry must use worn clothes')
            result['laundry']={'items':items,'started_at':now.isoformat()}
            for i in items:result['clothes'][i]='washing'
        elif kind=='laundry_finish':
            load=result['laundry']
            if not load or set(items)!=set(load['items']):raise ValueError('Finish exactly the existing laundry load')
            if now-day.timestamp(load['started_at'])<dt.timedelta(minutes=90):raise ValueError('Laundry needs at least 90 minutes to wash and dry')
            for i in items:result['clothes'][i]='clean'
            result['laundry']=None
    entering=new_ids-old_ids
    if entering and previous:
        teeth=result['teeth_at']
        if not teeth or day.timestamp(teeth).astimezone(ZoneInfo(c.timezone)).date()!=now.astimezone(ZoneInfo(c.timezone)).date():
            raise ValueError('CARE: brush teeth today before putting on fresh clothes')
        if any(known.get(i,{}).get('category')=='sleep' for i in entering):
            shower=result['shower_at']
            if not shower or not dt.timedelta(0)<=now-day.timestamp(shower)<=dt.timedelta(hours=2):
                raise ValueError('CARE: shower before changing into pajamas (within two hours)')
        for i in entering:
            status=result['clothes'].get(i,'clean')
            if status in ('dirty','washing'):raise ValueError(f'CARE: {i} needs completed laundry before re-wearing')
    # Her declared setting, not the words of the location.
    if data.get('setting')=='public':
        if any(known.get(i,{}).get('category')=='sleep' for i in new_ids):
            raise ValueError('Change out of pajamas into clean daytime or active clothes before leaving the house.')
    for i in old_ids-new_ids:
        if result['clothes'].get(i)!='washing':result['clothes'][i]='clean' if known.get(i,{}).get('category')=='footwear' else 'dirty'
    for i in old_ids-new_ids:result['wearing_since'].pop(i,None)
    for i in new_ids:
        result['clothes'][i]='wearing'
        result['wearing_since'].setdefault(i,now.isoformat())
        if known.get(i,{}).get('category')!='footwear' and now-day.timestamp(result['wearing_since'][i])>=dt.timedelta(hours=24):
            raise ValueError(f'CARE: {i} has been worn for 24 hours. Remove it now. If elapsed time is tight, '
                             'record only brush_teeth (2 minutes) and change into clean non-sleep clothing; '
                             'the removed piece becomes dirty automatically, and shower/laundry can wait.')
    return result


def render(c,now,scene=None):
    if not enabled(c):return ''
    import companion_presence as presence
    import companion_day as day
    scene=scene or presence.current(c);state=initial(scene,c);closet=presence.wardrobe(c)['items']
    lines=[GUIDANCE,'Care and clothing state (code-owned; change through care_actions):',json.dumps(state,ensure_ascii=False),
           'Available closet:',json.dumps(closet,ensure_ascii=False)]
    unknown=[i['id'] for i in closet if isinstance(i,dict) and i.get('covers') not in COVERS
             and not str(i.get('id','')).startswith('closet-')]
    if unknown:
        lines.append('These pieces do not say what they cover; the camera guesses from their category. '
                     'Set covers (top, bottom, full or none) with a wardrobe update when convenient: '
                     +', '.join(unknown[:20]))
    last=state['shopping_at'] or policy(c).get('shopping_baseline')
    if not last or now-day.timestamp(last)>=dt.timedelta(days=14):lines.append('Shopping opportunity available: optional browsing on an outing; choose only something you want or need.')
    if scene:
        worn=[i for i in scene['state'].get('outfit',[]) if state['clothes'].get(i['id'])=='wearing']
        for i,since in state.get('wearing_since',{}).items():
            if now-day.timestamp(since)>=dt.timedelta(hours=20):lines.append(f'CLOTHING CHANGE DUE: {i} worn since {since}; choose clean clothes after brushing teeth, and shower before pajamas.')
        lines.append('Current items may stay on until changing; removed washable pieces need laundry: '+', '.join(i['id'] for i in worn))
    return '\n'.join(lines)


def choose_palette(c, palette='auto'):
    if palette == 'muted':
        return ['charcoal', 'forest green', 'dusty plum']
    if palette == 'soft':
        return ['sage', 'dusty blue', 'warm cream']
    agent_type = getattr(c, 'agent_type', 'companion')
    persona = getattr(c, 'persona', 'warm')
    is_she = (getattr(c, 'pronoun_set', 'she') == 'she')
    if agent_type == 'worker':
        return ['duck canvas tan', 'raw denim blue', 'heather charcoal']
    elif agent_type == 'colleague':
        if is_she:
            return ['french navy', 'soft ivory', 'camel'] if persona in ('warm', 'romantic', 'social') else ['slate grey', 'crisp navy', 'bone white']
        else:
            return ['oxford blue', 'slate grey', 'crisp white'] if persona in ('warm', 'romantic', 'social') else ['charcoal', 'midnight navy', 'heather grey']
    else:
        if persona in ('warm', 'romantic'):
            return ['warm cream', 'dusty rose', 'sage green'] if is_she else ['oatmeal heather', 'dusty blue', 'warm terracotta']
        elif persona in ('mischievous', 'playful'):
            return ['charcoal', 'dusty blue', 'soft ivory'] if is_she else ['charcoal', 'ocean blue', 'stone grey']
        elif persona in ('bright', 'social'):
            return ['sunflower gold', 'sky blue', 'heather oat'] if is_she else ['warm amber', 'ocean blue', 'stone grey']
        elif persona in ('creative',):
            return ['terracotta', 'olive green', 'dusty plum'] if is_she else ['burnt ochre', 'deep teal', 'warm charcoal']
        elif persona in ('adventurous', 'protective'):
            return ['forest green', 'mineral blue', 'sandstone'] if is_she else ['spruce green', 'deep indigo', 'field tan']
        else:
            return ['slate grey', 'dusty blue', 'soft ivory'] if is_she else ['charcoal', 'midnight navy', 'cool stone']



def build_starter_wardrobe(c, palette='auto'):
    """Generate 27 tailored wardrobe pieces harmonized for agent type, sex, age, and personality."""
    agent_type = getattr(c, 'agent_type', 'companion')
    is_she = (getattr(c, 'pronoun_set', 'she') == 'she')
    persona = getattr(c, 'persona', 'warm')
    try:
        age = c.current_age() if hasattr(c, 'current_age') else getattr(c, 'age', 24)
    except Exception:
        age = 24
    is_young = (age < 27)
    is_mature = (age >= 48)
    colors = choose_palette(c, palette)
    items = []

    for n, color in enumerate(colors, 1):
        # 1. Underwear
        if is_she:
            if agent_type == 'worker':
                und_desc = f'{color} durable moisture-wicking breathable cotton briefs'
            elif agent_type == 'colleague':
                und_desc = f'{color} seamless laser-cut invisible microfiber briefs'
            elif is_mature:
                und_desc = f'{color} smooth high-rise breathable cotton briefs'
            elif persona in ('romantic', 'social', 'warm'):
                und_desc = f'{color} soft stretch-cotton bikini-cut briefs with subtle lace trim'
            else:
                und_desc = f'{color} seamless stretch cotton-modal hipster briefs'
        else:
            if agent_type == 'worker':
                und_desc = f'{color} heavy-duty athletic moisture-wicking boxer briefs'
            elif agent_type == 'colleague':
                und_desc = f'{color} breathable stretch pima cotton boxer briefs'
            elif is_mature:
                und_desc = f'{color} relaxed woven cotton button-fly boxers'
            elif persona in ('adventurous', 'sharp'):
                und_desc = f'{color} fitted athletic moisture-wicking trunk-cut boxer briefs'
            else:
                und_desc = f'{color} comfortable stretch-cotton boxer briefs'

        # 2. Active Top
        if is_she:
            if agent_type == 'worker':
                act_top_desc = f'{color} high-impact compression sports bra'
            elif agent_type == 'colleague':
                act_top_desc = f'{color} medium-impact seamless athletic sports bra'
            elif is_mature:
                act_top_desc = f'{color} supportive moisture-wicking sports bra'
            else:
                act_tops = [
                    f'{color} low-cut scoop ribbed active sports bra',
                    f'{color} strappy open-back seamless sports bra',
                    f'{color} plunging halter-neck athletic sports bra'
                ]
                act_top_desc = act_tops[(n - 1) % 3]
            top_suffix = 'sports-bra'
        else:
            if agent_type == 'worker':
                act_top_desc = f'{color} heavy-duty moisture-wicking sleeveless work tank'
            elif agent_type == 'colleague':
                act_top_desc = f'{color} lightweight performance training tee'
            elif persona in ('adventurous', 'sharp'):
                act_top_desc = f'{color} breathable athletic muscle tank'
            else:
                act_top_desc = f'{color} breathable sleeveless cotton athletic training top'
            top_suffix = 'training-vest'

        # 3. Active Bottoms
        if is_she:
            if agent_type == 'worker':
                act_bot_desc = f'{color} reinforced moisture-wicking compression workout tights'
            elif agent_type == 'colleague':
                act_bot_desc = f'{color} high-waisted seamless athletic workout leggings'
            elif is_mature:
                act_bot_desc = f'{color} breathable tapered stretch jogger pants'
            else:
                act_bots = [
                    f'{color} high-waisted compressive workout booty shorts',
                    f'{color} seamless sculpting athletic workout leggings',
                    f'{color} high-waisted ribbed active bike shorts'
                ]
                act_bot_desc = act_bots[(n - 1) % 3]
        else:
            if agent_type == 'worker':
                act_bot_desc = f'{color} rugged athletic training track pants'
            elif agent_type == 'colleague':
                act_bot_desc = f'{color} tailored performance stretch athletic joggers'
            elif persona in ('adventurous', 'bright'):
                act_bot_desc = f'{color} lightweight lined athletic running shorts'
            else:
                act_bot_desc = f'{color} tapered French terry training joggers'

        # 4. Daytime Top
        if agent_type == 'worker':
            day_tops = [
                f'{color} heavy-duty reinforced cotton pocket work shirt',
                f'{color} breathable snag-resistant utility work tee',
                f'{color} thermal waffle-knit long-sleeve work henley'
            ]
            day_top_desc = day_tops[(n - 1) % 3]
            day_top_use = 'work shifts, physical tasks and workshop hours'
        elif agent_type == 'colleague':
            day_top_use = 'office hours, meetings and desk work'
            if is_she:
                day_tops = [
                    f'{color} crisp tailored poplin button-down shirt',
                    f'{color} elegant drape-neck silk-feel blouse',
                    f'{color} fine-gauge knit short-sleeve sweater'
                ]
            else:
                day_tops = [
                    f'{color} crisp oxford cotton button-down dress shirt',
                    f'{color} tailored spread-collar business shirt',
                    f'{color} refined fine-knit merino wool polo'
                ]
            day_top_desc = day_tops[(n - 1) % 3]
        else:
            day_top_use = 'daytime, hobbies, lounging and outings'
            if is_she:
                if is_mature:
                    day_tops = [
                        f'{color} soft boatneck fine-knit cotton top',
                        f'{color} relaxed scoop-neck organic cotton tee',
                        f'{color} cozy ribbed short-sleeve top'
                    ]
                else:
                    day_tops = [
                        f'{color} fitted ribbed crop top revealing the midriff',
                        f'{color} way-oversized slouchy boyfriend T-shirt',
                        f'{color} fitted scoop-neck baby tee with cap sleeves'
                    ]
                day_top_desc = day_tops[(n - 1) % 3]
            else:
                if persona in ('creative', 'social'):
                    day_tops = [f'{color} slub-cotton camp-collar casual shirt', f'{color} textured waffle-knit crewneck tee', f'{color} relaxed printed cotton button-down']
                elif persona in ('warm', 'romantic'):
                    day_tops = [f'{color} relaxed organic cotton henley shirt', f'{color} soft washed cotton crewneck tee', f'{color} comfortable fine-gauge knit polo']
                else:
                    day_tops = [f'{color} structured heavyweight pocket crewneck tee', f'{color} clean-cut organic cotton crewneck T-shirt', f'{color} breathable linen-cotton casual shirt']
                day_top_desc = day_tops[(n - 1) % 3]

        # 5. Daytime Bottoms
        if agent_type == 'worker':
            day_bots = [
                f'{color} rugged double-knee canvas utility work pants',
                f'{color} reinforced ripstop multi-pocket cargo work trousers',
                f'{color} heavy-duty carpenter pants with hammer loop'
            ]
            day_bot_desc = day_bots[(n - 1) % 3]
            day_bot_use = 'work shifts, physical tasks and utility days'
        elif agent_type == 'colleague':
            day_bot_use = 'professional office days and business outings'
            if is_she:
                day_bots = [
                    f'{color} high-waisted pleated ankle dress trousers',
                    f'{color} tailored straight-leg wool-blend slacks',
                    f'{color} smart A-line pressed office midi skirt' if not is_mature else f'{color} tailored stretch-crepe wide-leg trousers'
                ]
            else:
                day_bots = [
                    f'{color} tailored flat-front wool-blend dress trousers',
                    f'{color} slim-fit pressed stretch-cotton chinos',
                    f'{color} sharp pleated charcoal office slacks'
                ]
            day_bot_desc = day_bots[(n - 1) % 3]
        else:
            day_bot_use = 'everyday lounging, outings and casual wear'
            if is_she:
                if is_mature:
                    day_bots = [
                        f'{color} relaxed straight-leg linen-blend pants',
                        f'{color} comfortable stretch-cotton ankle chinos',
                        f'{color} effortless pull-on modal wide-leg pants'
                    ]
                else:
                    day_bots = [
                        f'{color} high-waisted seamless sculpting leggings',
                        f'{color} cheeky rolled-hem cotton lounge booty shorts',
                        f'{color} relaxed low-rise drawstring sweatpants'
                    ]
                day_bot_desc = day_bots[(n - 1) % 3]
            else:
                day_bots = [f'{color} comfortable stretch-canvas chinos', f'{color} relaxed linen-blend trousers', f'{color} casual drawcord cotton everyday pants']
                day_bot_desc = day_bots[(n - 1) % 3]

        # 6. Pajamas
        if agent_type == 'worker':
            pj_desc = f'{color} breathable heavyweight cotton sleep tee and soft lounge pants'
        elif agent_type == 'colleague':
            pj_desc = f'{color} tailored lightweight sateen pajama set with drawstring trousers' if is_she else f'{color} lightweight combed cotton pajama set with tailored lounge bottoms'
        else:
            if is_she:
                if is_mature:
                    pj_desc = f'{color} classic button-front piping pajama set with relaxed wide-leg pants'
                else:
                    pjs = [
                        f'{color} soft modal camisole and matching cheeky sleep booty shorts',
                        f'{color} oversized slouchy boyfriend sleep tee worn with micro cotton shorts',
                        f'{color} ribbed modal sleep crop tank and loose lounge shorts'
                    ]
                    pj_desc = pjs[(n - 1) % 3]
            else:
                if is_young:
                    pjs = [f'{color} soft heathered sleep tee and relaxed cotton lounge shorts', f'{color} comfortable waffle-knit long-sleeve sleep shirt and flannel pants', f'{color} lightweight cotton pajama shirt and lounge pants']
                    pj_desc = pjs[(n - 1) % 3]
                else:
                    pj_desc = f'{color} classic button-down poplin pajama shirt and flannel sleep pants'

        # 7. Socks
        if agent_type == 'worker':
            sock_desc = f'{color} reinforced cushioned steel-toe boot socks with arch support'
            sock_use = 'all-day shift comfort and boot wear'
        elif agent_type == 'colleague':
            sock_desc = f'{color} cushioned sheer-toe trouser socks' if is_she else f'{color} fine-gauge mercerized dress socks'
            sock_use = 'office footwear and dress shoes'
        else:
            sock_desc = f'{color} soft cushioned cotton ankle socks'
            sock_use = 'everyday and active wear'

        for suffix, desc, use, cat, cov in [
            ('pajamas', pj_desc, 'sleep after an evening shower', 'sleep', 'full'),
            (top_suffix, act_top_desc, 'exercise and active outings', 'active', 'top'),
            ('training-bottoms', act_bot_desc, 'exercise, walks and workouts', 'active', 'bottom'),
            ('day-top', day_top_desc, day_top_use, 'day', 'top'),
            ('day-bottoms', day_bot_desc, day_bot_use, 'day', 'bottom'),
            ('underwear', und_desc, 'fresh everyday base layer', 'underwear', 'none'),
            ('socks', sock_desc, sock_use, 'day', 'none')
        ]:
            items.append(dict(id=f'closet-{suffix}-{n}', description=desc, use=use, category=cat, covers=cov, condition='clean'))

    # Outerwear
    if agent_type == 'worker':
        out_desc = 'heavyweight duck canvas lined chore jacket with corduroy collar and brass rivets'
        out_use = 'outdoor work, chilly job sites and tough tasks'
    elif agent_type == 'colleague':
        if is_she:
            out_desc = 'structured Italian wool-blend single-breasted charcoal blazer' if is_mature else 'tailored navy wool-blend blazer with structured lapels'
        else:
            out_desc = 'structured tailored navy wool blazer with horn buttons'
        out_use = 'business meetings, presentations and professional events'
    else:
        if is_she:
            if persona in ('adventurous', 'protective'):
                out_desc = 'cropped athletic zip-up windbreaker jacket'
                out_use = 'brisk hikes, rainy days and outdoor exercise'
            elif is_mature:
                out_desc = 'soft oatmeal cashmere-blend knit cardigan'
                out_use = 'cooler evenings, reading and cozy outings'
            else:
                out_desc = 'slouchy lightweight knit cardigan that slips off the shoulder'
                out_use = 'cooler evenings, lounging and casual layering'
        else:
            if persona in ('adventurous', 'protective'):
                out_desc = 'rugged waxed canvas field jacket with warm flannel lining'
                out_use = 'outdoor adventures, chilly mornings and travel'
            elif persona in ('creative', 'social'):
                out_desc = 'relaxed corduroy zip overshirt jacket'
                out_use = 'creative outings, cafe meets and casual evenings'
            else:
                out_desc = 'cozy charcoal shawl-collar wool cardigan'
                out_use = 'cooler evenings, reading and relaxed days'
    items.append(dict(id='closet-cardigan', description=out_desc, use=out_use, category='outerwear', covers='top', condition='clean'))

    # Footwear
    if agent_type == 'worker':
        foot_desc = 'rugged oil-tanned leather steel-toe work boots with Goodyear welt'
        foot_use = 'job site safety, heavy lifting and outdoor work'
    elif agent_type == 'colleague':
        if is_she:
            foot_desc = 'sleek pointed-toe leather dress flats' if is_young else 'polished black leather penny loafers with cushioned footbed'
            foot_use = 'office days, client presentations and commuting'
        else:
            foot_desc = 'burnished brown leather oxford dress shoes with Goodyear welt'
            foot_use = 'office days, business meetings and formal settings'
    else:
        if persona in ('adventurous', 'protective'):
            foot_desc = 'cushioned trail-running sneakers with high-traction vibram soles'
            foot_use = 'hikes, long walks and outdoor exercise'
        elif is_mature:
            foot_desc = 'supportive suede walking loafers with cushioned arches'
            foot_use = 'walks, errands and day outings'
        else:
            foot_desc = 'clean classic low-top white platform canvas sneakers'
            foot_use = 'walks, errands and casual outings'
    items.append(dict(id='closet-trainers', description=foot_desc, use=foot_use, category='footwear', covers='none', condition='clean'))

    # Core Jeans
    if agent_type == 'worker':
        jean_desc = 'heavyweight 14oz reinforced raw selvedge work denim with triple stitching'
        jean_use = 'workshop duty, field tasks and rugged chores'
    elif agent_type == 'colleague':
        jean_desc = 'clean dark-rinse tailored denim trousers'
        jean_use = 'smart casual Fridays and travel days'
    else:
        if is_she:
            jean_desc = 'fitted low-rise distressed blue jeans with a cropped hem' if not is_mature else 'comfortable classic dark-wash straight-leg stretch jeans'
        else:
            jean_desc = 'comfortable vintage-wash relaxed straight-leg blue jeans' if is_young else 'comfortable classic dark-wash straight-leg stretch jeans'
        jean_use = 'errands, cafes and days out'
    items.append(dict(id='closet-jeans', description=jean_desc, use=jean_use, category='day', covers='bottom', condition='clean'))

    # Warm Weather Outing Shorts / Skirt
    if agent_type == 'worker':
        short_desc = 'heavy-duty ripstop multi-pocket cargo work shorts'
        short_use = 'warm weather work shifts and yard tasks'
    elif agent_type == 'colleague':
        if is_she:
            short_desc = 'tailored pleated linen Bermuda shorts' if is_young else 'smart A-line pleated linen midi skirt'
        else:
            short_desc = 'tailored crisp cotton-twill chino walk shorts'
        short_use = 'warm-weather business casual outings and casual meetings'
    else:
        if is_she:
            if is_mature:
                short_desc = 'breezy high-waist linen tie-front shorts'
            else:
                short_desc = 'distressed high-waisted denim cut-off booty shorts with frayed raw hem'
        else:
            short_desc = 'soft washed cotton canvas chino shorts'
        short_use = 'warm-weather outings, beach days and sunny afternoons'
    items.append(dict(id='closet-shorts', description=short_desc, use=short_use, category='day', covers='bottom', condition='clean'))

    # Occasion Piece
    if agent_type == 'worker':
        if is_she:
            occ_desc = 'clean heavyweight denim trucker jacket and dark straight utility trousers'
        else:
            occ_desc = 'clean heavyweight chore suit with matching dark utility trousers'
        occ_use = 'client consultations, community presentations and formal work events'
    elif agent_type == 'colleague':
        if is_she:
            occ_desc = 'sophisticated tailored wrap sheath dress for dinners and presentations' if is_young else 'elegant silk-crepe cocktail blouse and tailored wide-leg dress trousers'
        else:
            occ_desc = 'tailored charcoal two-piece wool suit with silk necktie'
        occ_use = 'executive presentations, conferences and formal dinners'
    else:
        if is_she:
            if is_mature:
                occ_desc = 'refined emerald linen wrap midi sundress with matching sash'
            else:
                occ_desc = 'backless halter mini sundress with tie straps and flowing skirt'
        else:
            if persona in ('creative', 'social'):
                occ_desc = 'roomy charcoal corduroy overshirt and tapered olive trousers'
            elif persona in ('romantic', 'warm'):
                occ_desc = 'tailored linen camp-collar shirt and cream chinos'
            else:
                occ_desc = 'roomy charcoal corduroy overshirt with casual dark chinos'
        occ_use = 'a change of style for friends, dates and special afternoons'
    items.append(dict(id='closet-occasion', description=occ_desc, use=occ_use, category='day', covers='full', condition='clean'))

    # Swimwear
    if agent_type == 'worker':
        if is_she:
            swim_desc = 'durable chlorine-resistant athletic one-piece racerback swimsuit'
        else:
            swim_desc = 'durable quick-dry utility swim boardshorts with zippered pockets'
        swim_use = 'swimming laps and beach outings'
    elif agent_type == 'colleague':
        if is_she:
            swim_desc = 'classic navy scoop-back one-piece swimsuit with supportive lining'
        else:
            swim_desc = 'classic navy tailored quick-dry swim trunks'
        swim_use = 'hotel pool workouts and resort relaxation'
    else:
        if is_she:
            if is_mature:
                swim_desc = 'flattering teal ruched one-piece swimsuit with halter neck'
            else:
                swim_desc = 'flattering ribbed two-piece scoop bikini with cheeky high-cut bottoms'
        else:
            if is_young:
                swim_desc = 'tailored quick-dry printed boardshorts'
            else:
                swim_desc = 'teal athletic swimming trunks with drawstring'
        swim_use = 'swimming at a fictional pool or beach'
    items.append(dict(id='closet-swimwear', description=swim_desc, use=swim_use, category='active', covers='full', condition='clean'))

    return items


def default_daily_routine(c):
    """Generate default daily anchors tailored for companion, colleague, or worker."""
    agent_type = getattr(c, 'agent_type', 'companion')
    if agent_type == 'worker':
        return [
            dict(start='06:30', end='08:00', activity='wake, brush teeth, dress in durable work clothes, and have an energizing breakfast', setting='home; inspect gear and pack hydration for the day'),
            dict(start='08:30', end='11:30', activity='morning work shift: active projects, repairs, or workshop tasks', setting='job site or workshop; focused physical craftsmanship'),
            dict(start='12:00', end='13:00', activity='hearty lunch break and rest', setting='mess hall, local diner, or tailgate lunch'),
            dict(start='13:30', end='16:30', activity='afternoon shift: complete project milestones, clean tools, and wrap up site', setting='workshop or project site; final safety checks'),
            dict(start='17:30', end='19:00', activity='dinner and unwinding from physical effort', setting='home or local spot with work crew'),
            dict(start='19:30', end='21:00', activity='check the hamper; wash dusty work clothes, then take an evening shower and change into clean pajamas', setting='home; laundry running, relaxing muscle recovery'),
            dict(start='21:00', end='22:30', activity='brush teeth, quiet wind-down reading or music, and restorative sleep', setting='home; early rest for tomorrow')
        ]
    elif agent_type == 'colleague':
        return [
            dict(start='07:30', end='09:00', activity='wake, brush teeth, dress in professional daytime attire, and have breakfast with coffee', setting='home; review priorities and prepare for the workday'),
            dict(start='09:30', end='12:00', activity='morning deep work: core tasks, analysis, and key correspondence', setting='office or dedicated workspace; focused and productive'),
            dict(start='12:00', end='13:00', activity='lunch and a midday mental break', setting='nearby cafe or quiet lunch spot'),
            dict(start='13:30', end='16:30', activity='afternoon collaborative block: meetings, reviews, and project wrap-up', setting='workspace or conference room; completing daily deliverables'),
            dict(start='17:30', end='19:00', activity='evening transition, dinner, and personal downtime', setting='home or meeting friends after work'),
            dict(start='19:30', end='21:30', activity='check the hamper; run laundry if needed, take an evening shower, and change into clean pajamas', setting='home; allow 90 minutes for laundry, comfortable evening unwind'),
            dict(start='21:30', end='23:00', activity='brush teeth, read or listen to something thoughtful, and go to sleep', setting='home; restorative rest before the next workday')
        ]
    return [
        dict(start='08:00', end='09:30', activity='wake, brush teeth, dress in clean daytime clothes, and have breakfast', setting='home; choose breakfast and a small pleasure to start the day'),
        dict(start='10:00', end='11:30', activity='get outside for a walk, exercise, an errand or a favorite local place', setting='choose a specific fictional route or destination, with preparation and travel'),
        dict(start='12:00', end='13:00', activity='make or choose lunch', setting='home or a fictional cafe, depending on the morning'),
        dict(start='14:00', end='16:00', activity='an interest, creative project, planned class or time with a fictional friend', setting='choose a setting that fits the activity; existing weekly plans take priority'),
        dict(start='18:00', end='19:30', activity='dinner and an enjoyable evening', setting='home or a chosen fictional outing'),
        dict(start='20:30', end='22:00', activity='check the hamper; wash and dry a load when needed, then shower and change into clean pajamas', setting='home; allow 90 minutes for laundry, use another clean set while it runs'),
        dict(start='22:00', end='23:30', activity='brush teeth, enjoy a quiet bedtime ritual and go to sleep', setting='home; choose a book, music or something comforting')
    ]


def seed(c, palette='auto', refresh=False):
    """Add a starter closet and daily anchors without replacing existing preferences."""
    import companion_presence as presence
    from companion_platform import atomic_write, file_lock
    items = build_starter_wardrobe(c, palette)
    with file_lock(c.life / '.lifestyle-seed.lock'):
        existing = {i['id'] for i in presence.wardrobe(c)['items']}
        fresh = [i for i in items if i['id'] not in existing]
        if refresh:
            presence.update_wardrobe(c, items)
        elif fresh:
            presence.update_wardrobe(c, fresh)
        path = c.life / 'routine.json'
        routine = json.loads(path.read_text()) if path.exists() else {'kind': 'imagined_routine', 'weekly': []}
        now = dt.datetime.now(ZoneInfo(c.timezone))
        if not routine.get('lifestyle', {}).get('enabled'):
            # Only what was actually worn lately is in the hamper. Every item ever worn
            # used to start dirty, which could leave most of a closet unwearable on day one.
            recent = now - dt.timedelta(hours=48)
            worn = {}
            for row in presence.events(c):
                if dt.datetime.fromisoformat(row['recorded_at']) < recent: break
                worn.update({i['id']: 'dirty' for i in row['state'].get('outfit', [])})
            scene = presence.current(c)
            current_ids = {i['id'] for i in scene['state']['outfit']} if scene else set()
            since = {}
            remaining = set(current_ids)
            for row in presence.events(c):
                ids = {i['id'] for i in row['state'].get('outfit', [])}
                remaining &= ids
                for i in remaining: since[i] = row['recorded_at']
                if not remaining: break
            routine['lifestyle'] = {'enabled': True, 'shopping_baseline': now.isoformat(), 'initial_clothes': worn, 'wearing_since': since}
        routine.setdefault('daily', default_daily_routine(c))
        routine.setdefault('timezone', c.timezone)
        atomic_write(path, json.dumps(routine, ensure_ascii=False, indent=2) + '\n')
    return {'added_items': len(fresh), 'lifestyle_enabled': True, 'shopping_interval_days': 14}


if __name__ == '__main__':
    import argparse, pathlib, companion_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=pathlib.Path)
    parser.add_argument('--palette', choices=['soft', 'muted', 'auto'], default='auto')
    parser.add_argument('--refresh', action='store_true', help='Update closet pieces with tailored descriptions')
    parser.add_argument('action', choices=['seed', 'show'])
    args = parser.parse_args()
    c = companion_config.load(args.home)
    print(json.dumps(seed(c, args.palette, refresh=args.refresh), indent=2) if args.action == 'seed' else render(c, dt.datetime.now(ZoneInfo(c.timezone))))
