from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from xhtml2pdf import pisa
import os

# Configuração do Flask e SQLAlchemy 
app = Flask(__name__)

# Use apenas PostgreSQL (exige DATABASE_URL configurada no Render)
db_url = os.getenv('DATABASE_URL')
if not db_url:
    raise RuntimeError("A variável de ambiente DATABASE_URL não está configurada!")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sua senha secreta aqui')
app.config['UPLOAD_FOLDER'] = 'static/pdf'
db = SQLAlchemy(app)

#with app.app_context():
 #   db.create_all()

# Criar pasta de PDFs se não existir
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- Modelos do Banco de Dados ---
class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_nome = db.Column(db.String(100), nullable=False)
    cliente_telefone = db.Column(db.String(20))
    cliente_endereco = db.Column(db.String(200))  # Campo adicionado
    data = db.Column(db.DateTime, default=datetime.now)
    desconto = db.Column(db.Float, default=0.0)

    # Relacionamentos
    servicos = db.relationship('Servico', backref='orcamento', lazy=True)
    materiais = db.relationship('Material', backref='orcamento', lazy=True)

    def calcular_total(self):
        total_servicos = sum(
            servico.valor * servico.quantidade for servico in self.servicos
        )
        total_com_desconto = total_servicos - self.desconto
        return max(total_com_desconto, 0)  # Evita valores negativos

# ---- Modelo de Serviço Padrão ----
class ServicoPadrao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(10))  # 'm2' ou 'fixo'
    valor_padrao = db.Column(db.Float)

class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(10))  # 'm2' ou 'fixo'
    valor = db.Column(db.Float)
    quantidade = db.Column(db.Integer, default=1)  # Adicionado o campo quantidade
    orcamento_id = db.Column(db.Integer, db.ForeignKey('orcamento.id'))

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(200), nullable=False)
    quantidade = db.Column(db.String(50))
    orcamento_id = db.Column(db.Integer, db.ForeignKey('orcamento.id'))

class Recebimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_nome = db.Column(db.String(100))
    valor = db.Column(db.Float)
    data = db.Column(db.DateTime, default=datetime.now)
    orcamento_id = db.Column(db.Integer, db.ForeignKey('orcamento.id'))

# --- Rotas Principais ---
from datetime import datetime  # Certifique-se de que isso já está importado

@app.route('/')
def index():
    orcamentos = Orcamento.query.all()
    return render_template('index.html', orcamentos=orcamentos, datetime=datetime)

# ---- Rotas para Serviços Padrão ----
@app.route('/servicos-padrao')
def lista_servicos_padrao():
    servicos = ServicoPadrao.query.all()
    return render_template('servicos/lista.html', servicos=servicos, datetime=datetime)

@app.route('/servicos-padrao/novo', methods=['GET', 'POST'])
def criar_servico_padrao():
    if request.method == 'POST':
        novoServico = ServicoPadrao(
            descricao=request.form['descricao'],
            tipo=request.form['tipo'],
            valor_padrao=float(request.form['valor_padrao'])
        )
        db.session.add(novoServico)
        db.session.commit()
        flash('Serviço cadastrado!', 'success')
        return redirect(url_for('lista_servicos_padrao'))
    return render_template('servicos/novo.html', datetime=datetime)

@app.route('/servicos-padrao/<int:id>/editar', methods=['GET', 'POST'])
def editar_servico_padrao(id):
    servico = ServicoPadrao.query.get_or_404(id)
    if request.method == 'POST':
        servico.descricao = request.form['descricao']
        servico.tipo = request.form['tipo']
        servico.valor_padrao = float(request.form['valor_padrao'])
        db.session.commit()
        flash('Serviço atualizado com sucesso!', 'success')
        return redirect(url_for('lista_servicos_padrao'))
    return render_template('servicos/editar.html', servico=servico)

# rota para editar serviços padrão
@app.route('/servicos/<int:id>/editar', methods=['GET', 'POST'])
def editar_servico(id):
    servico = Servico.query.get_or_404(id)
    if request.method == 'POST':
        servico.descricao = request.form['descricao']
        servico.tipo = request.form['tipo']
        servico.valor = float(request.form['valor'])
        servico.quantidade = int(request.form['quantidade'])
        db.session.commit()
        flash('Serviço atualizado com sucesso!', 'success')
        return redirect(url_for('editar_orcamento', id=servico.orcamento_id))
    return render_template('servicos/editar.html', servico=servico)

# rota lista de orçamentos
@app.route('/orcamentos')
def lista_orcamentos():
    orcamentos = Orcamento.query.all()
    return render_template('orcamentos/lista.html', orcamentos=orcamentos, datetime=datetime)

# --- Rotas de Orçamentos ---
@app.route('/orcamentos/novo', methods=['GET', 'POST'])
def criar_orcamento():
    servicos_padrao = ServicoPadrao.query.all()  # Puxa serviços pré-cadastrados
    num_servicos = int(request.form.get('num_servicos', 1))  # Número inicial de serviços manuais

    if request.method == 'POST':
        # Verifica se o botão "Adicionar Serviço" foi clicado
        if 'adicionar_servico' in request.form:
            num_servicos += 1
            return render_template(
                'orcamentos/criar.html',
                servicos_padrao=servicos_padrao,
                num_servicos=num_servicos,
                cliente_nome=request.form.get('cliente_nome', ''),
                cliente_telefone=request.form.get('cliente_telefone', ''),
                cliente_endereco=request.form.get('cliente_endereco', ''),
                desconto=request.form.get('desconto', 0)
            )

        # Salvar orçamento
        novo_orcamento = Orcamento(
            cliente_nome=request.form['cliente_nome'],
            cliente_telefone=request.form['cliente_telefone'],
            cliente_endereco=request.form['cliente_endereco'],  
            desconto=float(request.form.get('desconto', 0))
        )
        db.session.add(novo_orcamento)
        db.session.commit()

        # Salvar serviços pré-cadastrados com quantidade
        for servico_padrao in servicos_padrao:
            quantidade = request.form.get(f'servico_padrao_{servico_padrao.id}_quantidade')
            if quantidade:
                novo_servico = Servico(
                    descricao=f"{servico_padrao.descricao} ({servico_padrao.tipo})",
                    tipo=servico_padrao.tipo,
                    valor=servico_padrao.valor_padrao,
                    quantidade=int(quantidade),
                    orcamento_id=novo_orcamento.id
                )
                db.session.add(novo_servico)

        # Salvar serviços manuais
        for i in range(1, num_servicos + 1):
            descricao = request.form.get(f'servico{i}_descricao')
            if descricao:
                tipo = request.form.get(f'servico{i}_tipo')
                valor = float(request.form.get(f'servico{i}_valor', 0))
                quantidade = int(request.form.get(f'servico{i}_quantidade', 0))
                novo_servico = Servico(
                    descricao=descricao,
                    tipo=tipo,
                    valor=valor,
                    quantidade=quantidade,
                    orcamento_id=novo_orcamento.id
                )
                db.session.add(novo_servico)

        # Salvar materiais
        material_descricao = request.form.get('material1_descricao')
        if material_descricao:
            novo_material = Material(
                descricao=material_descricao,
                quantidade='',  # ou algum valor padrão, se não tiver campo de quantidade
                orcamento_id=novo_orcamento.id
            )
            db.session.add(novo_material)
            db.session.commit()

        db.session.commit()
        flash('Orçamento criado com sucesso!', 'success')
        return redirect(url_for('lista_orcamentos'))

    return render_template('orcamentos/criar.html', servicos_padrao=servicos_padrao, num_servicos=num_servicos)

# rota para editar orçamentos
@app.route('/orcamentos/<int:id>/editar', methods=['GET', 'POST'])
def editar_orcamento(id):
    orcamento = Orcamento.query.get_or_404(id)
    servicos_padrao = ServicoPadrao.query.all()  # Adiciona os serviços pré-cadastrados

    if request.method == 'POST':
        try:
            # Atualizar os dados do cliente
            orcamento.cliente_nome = request.form['cliente_nome']
            orcamento.cliente_telefone = request.form['cliente_telefone']
            orcamento.cliente_endereco = request.form['cliente_endereco']
            orcamento.desconto = float(request.form.get('desconto', 0))

            # Atualizar os serviços
            orcamento.servicos.clear()
            for key, value in request.form.items():
                if key.startswith('servicos['):
                    field = key.split('[')[2].split(']')[0]
                    servico_id = key.split('[')[1].split(']')[0]
                    if field == 'descricao':
                        descricao = value
                        tipo = request.form[f'servicos[{servico_id}][tipo]']
                        valor = float(request.form[f'servicos[{servico_id}][valor]'])
                        quantidade = int(request.form[f'servicos[{servico_id}][quantidade]'])
                        novo_servico = Servico(
                            descricao=descricao,
                            tipo=tipo,
                            valor=valor,
                            quantidade=quantidade,
                            orcamento_id=orcamento.id
                        )
                        db.session.add(novo_servico)

            db.session.commit()
            return jsonify({'success': True, 'redirect': url_for('detalhes_orcamento', id=id)})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

    return render_template('orcamentos/editar.html', orcamento=orcamento, servicos_padrao=servicos_padrao)


# rota para excluir orçamentos
@app.route('/orcamentos/<int:id>/excluir', methods=['POST'])
def excluir_orcamento(id):
    orcamento = Orcamento.query.get_or_404(id)
    db.session.delete(orcamento)
    db.session.commit()
    flash('Orçamento excluído!', 'success')
    return redirect(url_for('lista_orcamentos'))

@app.route('/orcamentos/<int:id>/detalhes')
def detalhes_orcamento(id):
    orcamento = Orcamento.query.get_or_404(id)
    return render_template('orcamentos/detalhes.html', orcamento=orcamento, datetime=datetime)

@app.route('/orcamentos/<int:id>/gerar-pdf')
def gerar_pdf(id):
    orcamento = Orcamento.query.get_or_404(id)
    html = render_template('orcamentos/pdf_template.html', orcamento=orcamento)
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"orcamento_{id}.pdf")

    with open(pdf_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(html, dest=pdf_file)
        if pisa_status.err:
            flash('Erro ao gerar PDF', 'danger')
            return redirect(url_for('detalhes_orcamento', id=id))

    return send_from_directory(app.config['UPLOAD_FOLDER'], f"orcamento_{id}.pdf", as_attachment=True)

# --- Rotas de Recebimentos ---
@app.route('/recebimentos')
def lista_recebimentos():
    recebimentos = Recebimento.query.all()
    return render_template('recebimentos/lista.html', recebimentos=recebimentos, datetime=datetime)

@app.route('/recebimentos/novo', methods=['GET', 'POST'])
def adicionar_recebimento():
    orcamentos = Orcamento.query.all()  # Adicione esta linha
    if request.method == 'POST':
        novo_recebimento = Recebimento(
            cliente_nome=request.form['cliente_nome'],
            valor=float(request.form['valor']),
            orcamento_id=request.form.get('orcamento_id')
        )
        db.session.add(novo_recebimento)
        db.session.commit()
        flash('Recebimento registrado!', 'success')
        return redirect(url_for('lista_recebimentos'))
    return render_template('recebimentos/adicionar.html', datetime=datetime, orcamentos=orcamentos)

@app.route('/orcamentos/<int:id>/adicionar-servico', methods=['POST'])
def adicionar_servico_ajax(id):
    orcamento = Orcamento.query.get_or_404(id)
    data = request.get_json()
    servico_id = data.get('servico_id')

    if not servico_id:
        return jsonify({'success': False, 'message': 'Serviço não selecionado.'}), 400

    servico_padrao = ServicoPadrao.query.get(servico_id)
    if not servico_padrao:
        return jsonify({'success': False, 'message': 'Serviço não encontrado.'}), 404

    novo_servico = Servico(
        descricao=servico_padrao.descricao,
        tipo=servico_padrao.tipo,
        valor=servico_padrao.valor_padrao,
        quantidade=1,  # Quantidade padrão
        orcamento_id=orcamento.id
    )
    db.session.add(novo_servico)
    db.session.commit()

    return jsonify({
        'success': True,
        'servico': {
            'id': novo_servico.id,
            'descricao': novo_servico.descricao,
            'tipo': novo_servico.tipo,
            'valor': novo_servico.valor,
            'quantidade': novo_servico.quantidade
        }
    })


@app.route('/orcamentos/<int:id>/remover-servico/<int:servico_id>', methods=['POST'])
def remover_servico_ajax(id, servico_id):
    orcamento = Orcamento.query.get_or_404(id)
    servico = Servico.query.get_or_404(servico_id)

    if servico.orcamento_id != orcamento.id:
        return jsonify({'success': False, 'message': 'Serviço não pertence a este orçamento.'}), 400

    db.session.delete(servico)
    db.session.commit()

    return jsonify({'success': True})


# --- Inicialização ---
if __name__ == '__main__':
    app.run(debug=False)