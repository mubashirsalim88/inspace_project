from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# PostgreSQL config
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgres:1234567890@localhost/final_inspace'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Example model
class TestTable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))

    def __repr__(self):
        return f'<TestTable {self.name}>'

@app.route('/')
def index():
    # Insert an entry if not exists
    if not TestTable.query.first():
        db.session.add(TestTable(name="Shruti"))
        db.session.commit()
    
    data = TestTable.query.all()
    return '<br>'.join([f'{d.id}: {d.name}' for d in data])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if not exist
    app.run(debug=True)
