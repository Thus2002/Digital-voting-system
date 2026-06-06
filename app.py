from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import hashlib
import json
import time
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'blockchain_evoting_secret_2024'

ADMIN_PASSWORD = "admin123"

# ─── Blockchain Implementation ───────────────────────────────────────────────

class Block:
    def __init__(self, index, data, previous_hash):
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.hash = self.compute_hash()

    def compute_hash(self):
        block_string = json.dumps({
            'index': self.index,
            'timestamp': self.timestamp,
            'data': self.data,
            'previous_hash': self.previous_hash
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()


class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self._create_genesis_block()

    def _create_genesis_block(self):
        genesis = Block(0, "Genesis Block", "0")
        self.chain.append(genesis)

    def add_block(self, data):
        prev_hash = self.chain[-1].hash
        block = Block(len(self.chain), data, prev_hash)
        self.chain.append(block)
        return block

    def is_valid(self):
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            if current.hash != current.compute_hash():
                return False
            if current.previous_hash != previous.hash:
                return False
        return True

    def get_blocks_info(self):
        return [{
            'index': b.index,
            'timestamp': datetime.fromtimestamp(b.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            'data': b.data,
            'hash': b.hash[:20] + '...',
            'full_hash': b.hash,
            'previous_hash': b.previous_hash[:20] + '...'
        } for b in self.chain]


# ─── In-Memory Data Store ─────────────────────────────────────────────────────

blockchain = Blockchain()

voters = {}       # voter_id -> {name, has_voted, vote}
candidates = []   # list of candidate names
election_phase = "setup"   # setup | active | closed
votes = {}        # candidate -> count


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('voter_id'):
            return redirect(url_for('voter_login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ─── Home ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html',
                           logged_in=session.get('voter_id'),
                           admin=session.get('admin'))


# ─── Voter Registration ───────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        voter_id = request.form.get('voter_id', '').strip()
        password = request.form.get('password', '').strip()

        if not name or not voter_id or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if voter_id in voters:
            flash('Voter ID already registered.', 'error')
            return render_template('register.html')

        voters[voter_id] = {
            'name': name,
            'password': hashlib.sha256(password.encode()).hexdigest(),
            'has_voted': False,
            'vote': None
        }
        blockchain.add_block(f"Voter registered: {voter_id}")
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('voter_login'))

    return render_template('register.html')


# ─── Voter Login ──────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        voter_id = request.form.get('voter_id', '').strip()
        password = request.form.get('password', '').strip()
        hashed = hashlib.sha256(password.encode()).hexdigest()

        voter = voters.get(voter_id)
        if voter and voter['password'] == hashed:
            session['voter_id'] = voter_id
            session['voter_name'] = voter['name']
            flash(f'Welcome, {voter["name"]}!', 'success')
            return redirect(url_for('vote'))
        flash('Invalid credentials.', 'error')

    return render_template('voter_login.html')


@app.route('/logout')
def logout():
    session.pop('voter_id', None)
    session.pop('voter_name', None)
    session.pop('admin', None)
    return redirect(url_for('index'))


# ─── Voting ───────────────────────────────────────────────────────────────────

@app.route('/vote', methods=['GET', 'POST'])
@login_required
def vote():
    voter_id = session['voter_id']
    voter = voters[voter_id]

    if election_phase != 'active':
        flash('Voting is not currently active.', 'error')
        return render_template('vote.html', candidates=candidates,
                               has_voted=voter['has_voted'],
                               phase=election_phase)

    if request.method == 'POST':
        if voter['has_voted']:
            flash('You have already voted!', 'error')
            return redirect(url_for('vote'))

        candidate = request.form.get('candidate')
        if candidate not in candidates:
            flash('Invalid candidate.', 'error')
            return redirect(url_for('vote'))

        voter['has_voted'] = True
        voter['vote'] = candidate
        votes[candidate] = votes.get(candidate, 0) + 1
        blockchain.add_block(f"Vote cast by {voter_id} for {candidate}")
        blockchain.pending_transactions = []
        flash('Your vote has been recorded on the blockchain!', 'success')
        return redirect(url_for('results'))

    return render_template('vote.html', candidates=candidates,
                           has_voted=voter['has_voted'],
                           phase=election_phase)


# ─── Results ─────────────────────────────────────────────────────────────────

@app.route('/results')
def results():
    total = sum(votes.values()) if votes else 0
    results_data = []
    for c in candidates:
        count = votes.get(c, 0)
        pct = round((count / total * 100), 1) if total > 0 else 0
        results_data.append({'name': c, 'votes': count, 'percentage': pct})
    results_data.sort(key=lambda x: x['votes'], reverse=True)
    return render_template('results.html', results=results_data,
                           total=total, phase=election_phase)


# ─── Blockchain Viewer ────────────────────────────────────────────────────────

@app.route('/blockchain')
def view_blockchain():
    valid = blockchain.is_valid()
    blocks = blockchain.get_blocks_info()
    return render_template('blockchain.html', blocks=blocks, valid=valid,
                           count=len(blockchain.chain))


# ─── Admin Login ─────────────────────────────────────────────────────────────

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if pwd == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        flash('Invalid admin password.', 'error')
    return render_template('admin_login.html')


# ─── Admin Panel ─────────────────────────────────────────────────────────────

@app.route('/admin/panel', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    global election_phase

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_candidate':
            name = request.form.get('candidate_name', '').strip()
            if name and name not in candidates:
                candidates.append(name)
                votes[name] = 0
                flash(f'Candidate "{name}" added.', 'success')
            else:
                flash('Invalid or duplicate candidate name.', 'error')

        elif action == 'remove_candidate':
            name = request.form.get('candidate_name', '').strip()
            if name in candidates:
                candidates.remove(name)
                votes.pop(name, None)
                flash(f'Candidate "{name}" removed.', 'success')

        elif action == 'set_phase':
            election_phase = request.form.get('phase', 'setup')
            flash(f'Election phase set to: {election_phase}', 'success')

        return redirect(url_for('admin_panel'))

    stats = {
        'blocks': len(blockchain.chain),
        'pending': len(blockchain.pending_transactions),
        'chain_valid': blockchain.is_valid(),
        'registered_voters': len(voters),
        'votes_cast': sum(votes.values())
    }
    return render_template('admin_panel.html', candidates=candidates,
                           stats=stats, phase=election_phase, voters=voters)


@app.route('/admin/users')
@admin_required
def admin_users():
    return render_template('admin_users.html', voters=voters)


if __name__ == '__main__':
    app.run(debug=True)
