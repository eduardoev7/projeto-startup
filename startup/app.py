from flask import Flask, render_template_string, request, redirect, url_for, session
import json
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "classclean_secret"


# =========================
# BANCO DE DADOS SQLite
# =========================

DB_FILE = "classclean.db"


def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            nome  TEXT    NOT NULL UNIQUE,
            senha TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS turmas (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nome   TEXT    NOT NULL UNIQUE,
            pontos INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            turma_id  INTEGER NOT NULL REFERENCES turmas(id),
            titulo    TEXT    NOT NULL,
            descricao TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id   INTEGER NOT NULL REFERENCES usuarios(id),
            turma_id     INTEGER NOT NULL REFERENCES turmas(id),
            titulo       TEXT    NOT NULL,
            descricao    TEXT    NOT NULL,
            concluida_em TEXT    NOT NULL
        )
    """)

    for nome, senha in [("admin","1234"),("joao","abc123"),("maria","senha456"),("pedro","pedro789")]:
        cur.execute("INSERT OR IGNORE INTO usuarios (nome, senha) VALUES (?, ?)", (nome, senha))

    for t in ["Grupo A", "Grupo B"]:
        cur.execute("INSERT OR IGNORE INTO turmas (nome) VALUES (?)", (t,))

    conn.commit()
    conn.close()


def migrar_json():
    path = "usuarios.json"
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
        conn = get_db()
        cur  = conn.cursor()
        for nome, senha in dados.items():
            cur.execute("INSERT OR IGNORE INTO usuarios (nome, senha) VALUES (?, ?)", (nome, senha))
        conn.commit()
        conn.close()
        os.rename(path, path + ".migrado")
    except Exception as e:
        print(f"[migração] {e}")


# =========================
# HELPERS
# =========================

def verificar_usuario(nome, senha):
    conn = get_db()
    row  = conn.execute("SELECT id FROM usuarios WHERE nome=? AND senha=?", (nome, senha)).fetchone()
    conn.close()
    return row["id"] if row else None


def cadastrar_usuario(nome, senha):
    conn = get_db()
    try:
        if conn.execute("SELECT id FROM usuarios WHERE nome=?", (nome,)).fetchone():
            return False
        conn.execute("INSERT INTO usuarios (nome, senha) VALUES (?, ?)", (nome, senha))
        conn.commit()
        return True
    finally:
        conn.close()


def buscar_grupo():
    conn  = get_db()
    grupo = {}
    for t in conn.execute("SELECT id, nome, pontos FROM turmas ORDER BY nome").fetchall():
        tarefas = conn.execute(
            "SELECT id, titulo, descricao FROM tarefas WHERE turma_id=? ORDER BY id",
            (t["id"],)
        ).fetchall()
        grupo[t["nome"]] = {
            "id":      t["id"],
            "pontos":  t["pontos"],
            "tarefas": [{"id": r["id"], "titulo": r["titulo"], "descricao": r["descricao"]} for r in tarefas]
        }
    conn.close()
    return grupo


def adicionar_tarefa(grupo_nome, titulo, descricao):
    conn = get_db()
    row  = conn.execute("SELECT id FROM turmas WHERE nome=?", (grupo_nome,)).fetchone()
    if row:
        conn.execute("INSERT INTO tarefas (turma_id, titulo, descricao) VALUES (?,?,?)",
                     (row["id"], titulo, descricao))
        conn.commit()
    conn.close()


def concluir_tarefa(tarefa_id, usuario_id):
    conn   = get_db()
    tarefa = conn.execute("SELECT turma_id, titulo, descricao FROM tarefas WHERE id=?", (tarefa_id,)).fetchone()
    if tarefa:
        conn.execute(
            "INSERT INTO historico (usuario_id, turma_id, titulo, descricao, concluida_em) VALUES (?,?,?,?,?)",
            (usuario_id, tarefa["turma_id"], tarefa["titulo"], tarefa["descricao"],
             datetime.now().strftime("%d/%m/%Y %H:%M"))
        )
        conn.execute("DELETE FROM tarefas WHERE id=?", (tarefa_id,))
        conn.execute("UPDATE turmas SET pontos = pontos + 10 WHERE id=?", (tarefa["turma_id"],))
        conn.commit()
    conn.close()


def buscar_historico(usuario_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT h.titulo, h.descricao, h.concluida_em, t.nome AS turma
        FROM historico h
        JOIN turmas t ON t.id = h.turma_id
        WHERE h.usuario_id = ?
        ORDER BY h.id DESC
    """, (usuario_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =========================
# HTML LOGIN
# =========================

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Class Clean — Login</title>
<style>
body{margin:0;font-family:Arial;background:linear-gradient(135deg,#1a3c34,#0f2a4a);height:100vh;display:flex;justify-content:center;align-items:center;}
.box{background:#fff;width:360px;padding:45px 40px;border-radius:20px;text-align:center;box-shadow:0 12px 40px rgba(0,0,0,.4);}
.box h1{color:#1a3c34;margin-bottom:8px;}
.box p{color:#777;font-size:14px;margin-bottom:10px;}
input{width:100%;padding:12px 14px;margin-top:12px;border:2px solid #e0e0e0;border-radius:10px;background:#f8faf9;color:#333;font-size:15px;outline:none;box-sizing:border-box;transition:border-color .2s;}
input:focus{border-color:#2e7d52;}
button{width:100%;padding:13px;margin-top:18px;border:none;border-radius:10px;background:linear-gradient(135deg,#2e7d52,#1a3c34);color:#fff;font-size:15px;font-weight:bold;cursor:pointer;transition:opacity .2s;}
button:hover{opacity:.88;}
.link-area{margin-top:18px;}
a{text-decoration:none;color:#2e7d52;font-weight:bold;font-size:14px;}
a:hover{text-decoration:underline;}
.erro{color:#c0392b;margin-top:14px;font-size:14px;font-weight:bold;}
</style>
</head>
<body>
<div class="box">
  <h1>Login</h1>
  <p>Faça login para continuar</p>
  <form method="POST">
    <input type="text"     name="usuario" placeholder="Usuário" required>
    <input type="password" name="senha"   placeholder="Senha"   required>
    <button type="submit">Entrar</button>
  </form>
  <div class="link-area"><a href="/register">Criar conta</a></div>
  {% if erro %}<div class="erro">Usuário ou senha inválidos</div>{% endif %}
</div>
</body>
</html>
"""


# =========================
# HTML CADASTRO
# =========================

REGISTER_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Class Clean — Criar Conta</title>
<style>
body{margin:0;font-family:Arial;background:linear-gradient(135deg,#1a3c34,#0f2a4a);height:100vh;display:flex;justify-content:center;align-items:center;}
.box{background:#fff;width:360px;padding:45px 40px;border-radius:20px;text-align:center;box-shadow:0 12px 40px rgba(0,0,0,.4);}
.box h1{color:#1a3c34;margin-bottom:8px;}
.box p{color:#777;font-size:14px;margin-bottom:10px;}
input{width:100%;padding:12px 14px;margin-top:12px;border:2px solid #e0e0e0;border-radius:10px;background:#f8faf9;color:#333;font-size:15px;outline:none;box-sizing:border-box;transition:border-color .2s;}
input:focus{border-color:#2e7d52;}
button{width:100%;padding:13px;margin-top:18px;border:none;border-radius:10px;background:linear-gradient(135deg,#2e7d52,#1a3c34);color:#fff;font-size:15px;font-weight:bold;cursor:pointer;transition:opacity .2s;}
button:hover{opacity:.88;}
.link-area{margin-top:18px;}
a{text-decoration:none;color:#2e7d52;font-weight:bold;font-size:14px;}
a:hover{text-decoration:underline;}
.msg{margin-top:15px;color:#2e7d52;font-weight:bold;font-size:14px;}
.erro{margin-top:15px;color:#c0392b;font-weight:bold;font-size:14px;}
</style>
</head>
<body>
<div class="box">
  <h1>Criar Usuário</h1>
  <p>Preencha os dados abaixo</p>
  <form method="POST">
    <input type="text"     name="usuario" placeholder="Novo usuário" required>
    <input type="password" name="senha"   placeholder="Nova senha"   required>
    <button type="submit">Cadastrar</button>
  </form>
  <div class="link-area"><a href="/">Voltar para login</a></div>
  {% if msg  %}<div class="msg" >{{ msg  }}</div>{% endif %}
  {% if erro %}<div class="erro">{{ erro }}</div>{% endif %}
</div>
</body>
</html>
"""


# =========================
# HTML PRINCIPAL
# =========================

HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Class Clean</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:Arial;}
body{background:linear-gradient(135deg,#1a3c34,#0f2a4a);min-height:100vh;padding:30px;color:#fff;}
.container{max-width:1200px;margin:auto;}
.topo-nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:30px;}
.topo-nav h1{font-size:2rem;letter-spacing:1px;}
.topo-nav p{color:#a8d5b5;font-size:14px;margin-top:4px;}
.nav-links{display:flex;gap:10px;}
.btn-nav{padding:10px 18px;border-radius:10px;text-decoration:none;font-weight:bold;font-size:14px;transition:opacity .2s;}
.btn-hist{background:linear-gradient(135deg,#2e7d52,#1a5c3a);color:#fff;}
.btn-sair{background:linear-gradient(135deg,#c0392b,#96281b);color:#fff;}
.btn-nav:hover{opacity:.85;}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px;}
.card{background:#fff;color:#2c2c2c;padding:28px;border-radius:20px;box-shadow:0 6px 24px rgba(0,0,0,.25);}
.card h2{color:#1a3c34;margin-bottom:12px;font-size:1.1rem;}
.card h3{color:#2e7d52;margin-top:16px;margin-bottom:4px;}
input,select{width:100%;padding:11px 13px;margin-top:10px;border:2px solid #e0e0e0;border-radius:10px;background:#f8faf9;color:#333;font-size:14px;outline:none;box-sizing:border-box;transition:border-color .2s;}
input:focus,select:focus{border-color:#2e7d52;}
button{width:100%;padding:12px;margin-top:14px;border:none;border-radius:10px;background:linear-gradient(135deg,#2e7d52,#1a3c34);color:#fff;font-size:14px;font-weight:bold;cursor:pointer;transition:opacity .2s;}
button:hover{opacity:.88;}
.tarefa{background:#f0f7f3;border-left:4px solid #2e7d52;padding:12px 14px;border-radius:10px;margin-top:10px;}
.tarefa strong{color:#1a3c34;}
.tarefa p{color:#555;font-size:13px;margin-top:4px;}
.done{display:inline-block;margin-top:10px;text-decoration:none;background:linear-gradient(135deg,#d4a017,#b8860b);color:#fff;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:bold;transition:opacity .2s;}
.done:hover{opacity:.85;}
.ranking-item{background:linear-gradient(135deg,#f0f7f3,#e6f2eb);border-left:4px solid #d4a017;padding:11px 14px;border-radius:10px;margin-top:10px;color:#1a3c34;font-size:14px;}
.ranking-item strong{color:#b8860b;}
.pontos{font-size:13px;color:#2e7d52;font-weight:bold;}
</style>
</head>
<body>
<div class="container">

  <div class="topo-nav">
    <div>
      <h1>Class Clean</h1>
      <p>Bem-vindo, {{ usuario }} 🙂</p>
    </div>
    <div class="nav-links">
      <a class="btn-nav btn-hist" href="/historico">📜 Meu Histórico</a>
      <a class="btn-nav btn-sair" href="/logout">Sair</a>
    </div>
  </div>

  <div class="cards">

    <div class="card">
      <h2>➕ Nova Tarefa</h2>
      <form action="/add" method="POST">
        <select name="grupo" required>
          {% for nome in grupo.keys() %}
          <option value="{{ nome }}">{{ nome }}</option>
          {% endfor %}
        </select>
        <input type="text" name="titulo"    placeholder="Título da tarefa"    required>
        <input type="text" name="descricao" placeholder="Descrição da tarefa" required>
        <button type="submit">Adicionar Tarefa</button>
      </form>
    </div>

    <div class="card">
      <h2>📋 Tarefas por Grupo</h2>
      {% for nome, dados in grupo.items() %}
        <h3>{{ nome }}</h3>
        <p class="pontos">🏆 {{ dados.pontos }} pontos</p>
        {% if dados.tarefas %}
          {% for tarefa in dados.tarefas %}
          <div class="tarefa">
            <strong>{{ tarefa.titulo }}</strong>
            <p>{{ tarefa.descricao }}</p>
            <a class="done" href="/done/{{ tarefa.id }}">✔ Concluir</a>
          </div>
          {% endfor %}
        {% else %}
          <p style="color:#aaa;font-size:13px;margin-top:6px;">Nenhuma tarefa</p>
        {% endif %}
      {% endfor %}
    </div>

    <div class="card">
      <h2>🏅 Ranking</h2>
      {% for nome, dados in ranking %}
      <div class="ranking-item">
        {{ nome }} — <strong>{{ dados.pontos }} pts</strong>
      </div>
      {% endfor %}
    </div>

  </div>
</div>
</body>
</html>
"""


# =========================
# HTML HISTÓRICO
# =========================

HISTORICO_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Class Clean — Histórico</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:Arial;}
body{background:linear-gradient(135deg,#1a3c34,#0f2a4a);min-height:100vh;padding:30px;color:#fff;}
.container{max-width:800px;margin:auto;}
.topo{display:flex;justify-content:space-between;align-items:center;margin-bottom:30px;}
.topo h1{font-size:1.8rem;}
.topo p{color:#a8d5b5;font-size:14px;margin-top:4px;}
a.voltar{padding:10px 18px;border-radius:10px;background:linear-gradient(135deg,#2e7d52,#1a5c3a);color:#fff;text-decoration:none;font-weight:bold;font-size:14px;transition:opacity .2s;}
a.voltar:hover{opacity:.85;}
.card{background:#fff;color:#2c2c2c;padding:28px;border-radius:20px;box-shadow:0 6px 24px rgba(0,0,0,.25);}
.card h2{color:#1a3c34;margin-bottom:16px;}
.item{background:#f0f7f3;border-left:4px solid #2e7d52;padding:12px 14px;border-radius:10px;margin-top:10px;}
.item strong{color:#1a3c34;font-size:15px;}
.item p{color:#555;font-size:13px;margin-top:3px;}
.item .meta{color:#2e7d52;font-size:12px;margin-top:6px;font-weight:bold;}
.vazio{color:#aaa;font-size:14px;text-align:center;padding:20px 0;}
</style>
</head>
<body>
<div class="container">
  <div class="topo">
    <div>
      <h1>📜 Histórico de {{ usuario }}</h1>
      <p>Todas as tarefas que você concluiu</p>
    </div>
    <a class="voltar" href="/home">← Voltar</a>
  </div>

  <div class="card">
    <h2>Tarefas Concluídas</h2>
    {% if historico %}
      {% for h in historico %}
      <div class="item">
        <strong>{{ h.titulo }}</strong>
        <p>{{ h.descricao }}</p>
        <div class="meta">📚 {{ h.turma }} &nbsp;|&nbsp; ✅ {{ h.concluida_em }}</div>
      </div>
      {% endfor %}
    {% else %}
      <div class="vazio">Nenhuma tarefa concluída ainda.</div>
    {% endif %}
  </div>
</div>
</body>
</html>
"""


# =========================
# ROTAS
# =========================

@app.route("/", methods=["GET", "POST"])
def login():
    erro = False
    if request.method == "POST":
        nome  = request.form.get("usuario", "").strip()
        senha = request.form.get("senha",   "")
        uid   = verificar_usuario(nome, senha)
        if uid:
            session["logado"]     = True
            session["usuario"]    = nome
            session["usuario_id"] = uid
            return redirect(url_for("home"))
        erro = True
    return render_template_string(LOGIN_HTML, erro=erro)


@app.route("/register", methods=["GET", "POST"])
def register():
    msg = erro = ""
    if request.method == "POST":
        nome  = request.form.get("usuario", "").strip()
        senha = request.form.get("senha",   "")
        if cadastrar_usuario(nome, senha):
            msg  = "Conta criada com sucesso"
        else:
            erro = "Usuário já existe"
    return render_template_string(REGISTER_HTML, msg=msg, erro=erro)


@app.route("/home")
def home():
    if not session.get("logado"):
        return redirect(url_for("login"))
    grupo   = buscar_grupo()
    ranking = sorted(grupo.items(), key=lambda x: x[1]["pontos"], reverse=True)
    return render_template_string(HTML, grupo=grupo, ranking=ranking, usuario=session["usuario"])


@app.route("/add", methods=["POST"])
def add():
    if not session.get("logado"):
        return redirect(url_for("login"))
    grupo_nome = request.form.get("grupo",    "")
    titulo     = request.form.get("titulo",   "").strip()
    descricao  = request.form.get("descricao","").strip()
    if grupo_nome and titulo and descricao:
        adicionar_tarefa(grupo_nome, titulo, descricao)
    return redirect(url_for("home"))


@app.route("/done/<int:tarefa_id>")
def done(tarefa_id):
    if not session.get("logado"):
        return redirect(url_for("login"))
    concluir_tarefa(tarefa_id, session["usuario_id"])
    return redirect(url_for("home"))


@app.route("/historico")
def historico():
    if not session.get("logado"):
        return redirect(url_for("login"))
    hist = buscar_historico(session["usuario_id"])
    return render_template_string(HISTORICO_HTML, historico=hist, usuario=session["usuario"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================
# INICIALIZAÇÃO
# =========================

if __name__ == "__main__":
    init_db()
    migrar_json()
    app.run(host="0.0.0.0", debug=True, port=5002)
