from flask import Flask, render_template, redirect, request, app, abort, json
from redis import Redis
from celery import Celery
import markdown
import uuid
import datetime

app = Flask(__name__, 
    template_folder='app/templates',
    static_url_path='',
    static_folder='app/static')
app.config['CELERY_BROKER_URL'] = 'redis://redis:6379/1'
app.config['CELERY_RESULT_BACKEND'] = 'redis://redis:6379/1'

celery = Celery(app.name, 
    backend=app.config['CELERY_RESULT_BACKEND'],
    broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

from tasks import viennarna, intarna

redis = Redis(host='redis', port=6379)

@app.context_processor
def inject_global_vars():
    return dict(
        title='CNEAT',
        subtitle='The CNE Analysis Tool',
        footer='Built with <a target="_blank" href="http://flask.pocoo.org/">Flask</a>'
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analysis/<uid>')
def analysis(uid):
    # make sure the analysis exists
    if not redis.exists('analyses:' + uid):
        return abort(404)

    started = redis.get('analyses:' + uid + ':started').decode("utf-8")
    config = redis.get('analyses:' + uid + ':config').decode("utf-8")
    return render_template('analysis.html', uid=uid, config=config, started=started)

@app.route('/get_analysis_status/<uid>', methods=['POST'])
def get_analysis_status(uid):
    # make sure the analysis exists
    if not redis.exists('analyses:' + uid):
        return abort(404)

    tasks = redis.lrange('analyses:' + uid + ':tasks', 0, -1)

    statuses = []
    for t in tasks:
        t = json.loads(t.decode('UTF-8'))
        # get celery task status
        res = celery.AsyncResult(t['task_id'])
        status = res.state
        statuses.append({'name': t['task_name'], 'id': t['task_id'], 'status': status})
    return json.dumps({'success': True, 'statuses': statuses}), 200, {'ContentType':'application/json'} 

@app.route('/get_task_data/<tid>', methods=['POST'])
def get_task_data(tid):
    res = celery.AsyncResult(tid)
    if res.state == 'SUCCESS':
        # render markdown
        content = markdown.markdown(res.result)
        return json.dumps({'success': True, 'result': content}), 200, {'ContentType':'application/json'} 
    else:
        return abort(404)

@app.route('/new_analysis', methods=['POST'])
def new_analysis():    
    # get analysis start time
    started = datetime.datetime.utcnow().strftime("%H:%M:%S %Y-%m-%d")

    config = request.get_json(force=True)

    if config is None:
        return json.dumps({'success': False}), 400, {'ContentType':'application/json'}

    # generate a unique ID (chance of collision is basically impossible)
    uid = ''
    while(True):
        uid = str(uuid.uuid4())[:8]
        if not redis.exists('analyses:' + uid):
            redis.set('analyses:' + uid, uid)
            redis.set('analyses:' + uid + ':started', started)
            redis.set('analyses:' + uid + ':config', json.dumps(config))
            break
    
    if config['config']['task_rna_rna'] == True:
        t1 = viennarna.viennarna.delay("test1", "test2")
        redis.lpush('analyses:' + uid + ':tasks', 
            json.dumps({
                'task_name': 'viennarna', 
                'task_id': t1.task_id
            })
        )
        t2 = intarna.intarna.delay("test1", "test2")
        redis.lpush('analyses:' + uid + ':tasks', 
            json.dumps({
                'task_name': 'intarna', 
                'task_id': t2.task_id
            })
        )
    
    return json.dumps({'success': True, 'uid': uid}), 200, {'ContentType':'application/json'} 

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
    