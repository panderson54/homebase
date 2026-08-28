from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Room
from app.routes import main_bp
from app.routes.helpers import get_household_room_or_404


def _apply_form(room, form):
    room.name = form.get('name', '').strip()
    room.floor = form.get('floor', '').strip() or None


@main_bp.route('/rooms/new', methods=['POST'])
@login_required
def room_new():
    room = Room(household_id=current_user.household_id)
    _apply_form(room, request.form)
    if not room.name:
        flash('Give the room a name.', 'danger')
        return redirect(url_for('main.home', tab='rooms'))
    db.session.add(room)
    db.session.commit()
    return redirect(url_for('main.home', tab='rooms'))


@main_bp.route('/rooms/<int:room_id>/edit', methods=['GET', 'POST'])
@login_required
def room_edit(room_id):
    room = get_household_room_or_404(room_id)

    if request.method == 'POST':
        _apply_form(room, request.form)
        if not room.name:
            flash('Give the room a name.', 'danger')
            return redirect(url_for('main.room_edit', room_id=room.id))
        db.session.commit()
        return redirect(url_for('main.home', tab='rooms'))

    return render_template('rooms/edit.html', room=room)


@main_bp.route('/rooms/<int:room_id>/delete', methods=['POST'])
@login_required
def room_delete(room_id):
    room = get_household_room_or_404(room_id)
    db.session.delete(room)
    db.session.commit()
    return redirect(url_for('main.home', tab='rooms'))
