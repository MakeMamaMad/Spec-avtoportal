// В будущем сюда подключим SDK/скрипт показов. Пока — заглушка и флаг выключения.
import {CONFIG} from '../js/config.js';
const el = document.getElementById('ad-spot');
if(el && !CONFIG.NATIVE_ADS_ENABLED){
  el.style.display = 'none';
}
